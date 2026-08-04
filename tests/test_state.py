from pathlib import Path
import os
import shutil

import json
from jsonschema import Draft202012Validator
import yaml

from pml.obligations import Obligation, enumerate_architecture_obligations, enumerate_obligations
from pml.cli import main
from pml.project_state import (
    MAX_ARCHITECTURE_STATE_ENTRIES,
    MAX_BOUNDARY_SCAN_ENTRIES,
    MAX_PRODUCT_STATE_ENTRIES,
    MAX_PRODUCT_STATE_SCAN_ENTRIES,
    MAX_STATE_FILE_BYTES,
    LockedBindings,
    bindings_digest,
    canonical_hash,
    input_fingerprint,
    load_bindings,
    write_architecture_state,
    write_product_state,
    load_state,
    validate_architecture_state,
    validate_probe_evidence,
    validate_product_state,
)
from pml.status import architecture_status, derive_obligation_status, product_status
from pml.validator import load_document


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ORIGIN = {
    "report_id": "state_fixture",
    "report_digest": f"sha256:{'3' * 64}",
    "verifier": {
        "agent": "state fixture",
        "provider": "pml",
        "model": "fixture model",
        "effort": "low",
    },
}


def copy_example_layout(tmp_path: Path) -> tuple[Path, Path]:
    examples = tmp_path / "examples"
    shutil.copytree(ROOT / "examples", examples)
    return examples / "minimal.pml.yaml", examples / "product-repository"


def write_architecture_layout(
    tmp_path: Path,
    document: dict,
    architecture_bindings: dict,
) -> tuple[Path, Path, str]:
    product = tmp_path / "product"
    owner = tmp_path / "product-pml"
    owner.mkdir()
    manifest = owner / "definition.pml.yaml"
    manifest.write_text(yaml.safe_dump(document, sort_keys=False))
    product_bindings: dict = {}
    for obligation in enumerate_obligations(document):
        binding = product_bindings.setdefault(
            obligation.node_id,
            {"paths": ["src"], "verification": {}},
        )
        binding["verification"][obligation.id] = {"agent_judgment": 1.0}
    bindings = {
        "pml_bindings": "0.1",
        "bindings": product_bindings,
    }
    if architecture_bindings:
        bindings["architecture"] = architecture_bindings
    (owner / "bindings.yaml").write_text(
        yaml.safe_dump(bindings, sort_keys=False)
    )
    metadata = product / ".pml"
    metadata.mkdir(parents=True)
    (product / "src").mkdir()
    digest = bindings_digest(bindings)
    (metadata / "pml.lock").write_text(yaml.safe_dump({
        "pml_lock": "0.1",
        "definition": {
            "source": str(manifest),
            "revision": "approved",
            "digest": canonical_hash(document),
        },
        "bindings": {"digest": digest},
    }, sort_keys=False))
    return product, manifest, digest


def test_obligations_have_stable_ids() -> None:
    document, diagnostics = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert diagnostics == []
    assert document is not None
    obligations = list(enumerate_obligations(document))
    assert [item.id for item in obligations] == [
        "domains.notes.features.creation.rules.preserve_content",
        "domains.notes.features.creation.use_cases.create_note",
    ]


def test_cli_lists_independently_addressable_architecture_obligations(
    capsys,
) -> None:
    manifest = ROOT / "examples" / "architecture-decisions.pml.yaml"
    obligation_id = (
        "architecture.durable_store.constraints.preserve_committed_records"
    )

    assert main(["obligations", str(manifest)]) == 0
    assert obligation_id in capsys.readouterr().out.splitlines()

    assert main([
        "obligations",
        str(manifest),
        "architecture.durable_store",
    ]) == 0
    assert capsys.readouterr().out.splitlines() == [obligation_id]


def test_product_state_detects_changed_bound_input(tmp_path: Path) -> None:
    document, diagnostics = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert diagnostics == []
    assert document is not None
    node_id = "domains.notes.features.creation"
    node = document["domains"]["notes"]["features"]["creation"]

    product = tmp_path / "product"
    owner = tmp_path / "product-pml"
    owner.mkdir()
    (owner / "minimal.pml.yaml").write_text(
        (ROOT / "examples" / "minimal.pml.yaml").read_text()
    )
    source = product / "src" / "notes.py"
    source.parent.mkdir(parents=True)
    source.write_text("VERSION = 1\n")
    metadata = product / ".pml"
    state_dir = metadata / "state" / "domains" / "notes" / "features"
    state_dir.mkdir(parents=True)
    bindings = {
        "pml_bindings": "0.1",
        "bindings": {
            node_id: {
                "paths": ["src/notes.py"],
                "verification": {
                    f"{node_id}.rules.preserve_content": {
                        "probes": {"preserve_content": 1.0}
                    },
                    f"{node_id}.use_cases.create_note": {
                        "agent_judgment": 1.0
                    },
                },
            }
        },
    }
    (owner / "bindings.yaml").write_text(yaml.safe_dump(bindings, sort_keys=False))
    (metadata / "pml.lock").write_text(yaml.safe_dump({
        "pml_lock": "0.1",
        "definition": {
            "source": "../product-pml/minimal.pml.yaml",
            "revision": "approved-revision",
            "digest": canonical_hash(document),
        },
        "bindings": {"digest": bindings_digest(bindings)},
    }, sort_keys=False))
    obligations = {}
    for obligation in enumerate_obligations(document, node_id):
        obligations[obligation.id] = {"implemented": "unknown", "evidence": {}}
    state = {
        "pml_state": "0.1",
        "node": node_id,
        "definition_hash": canonical_hash(node),
        "bindings_digest": bindings_digest(bindings),
        "input_fingerprint": input_fingerprint(product, ["src/notes.py"]),
        "obligations": obligations,
    }
    state_path = state_dir / "creation.state.yaml"
    state_path.write_text(yaml.safe_dump(state, sort_keys=False))

    assert validate_product_state(
        product,
        document,
        definition_source=owner / "minimal.pml.yaml",
    ) == []
    source.write_text("VERSION = 2\n")
    changed = validate_product_state(
        product,
        document,
        definition_source=owner / "minimal.pml.yaml",
    )
    assert any(item.code == "sync-required" for item in changed)


def test_state_schema_rejects_authored_scores_and_freshness() -> None:
    schema = json.loads((ROOT / "schema" / "pml-state.schema.json").read_text())
    state = yaml.safe_load((ROOT / "examples" / "invalid-state.yaml").read_text())
    errors = list(Draft202012Validator(schema).iter_errors(state))
    messages = "\n".join(error.message for error in errors)
    assert "verification_score" in messages
    assert "freshness" in messages


def test_state_loader_rejects_legacy_evidence_without_report_origin(
    tmp_path: Path,
) -> None:
    state = yaml.safe_load((
        ROOT
        / "examples/product-repository/.pml/state/domains/notes/features/creation.state.yaml"
    ).read_text())
    obligation = "domains.notes.features.creation.rules.preserve_content"
    state["obligations"][obligation]["evidence"]["deterministic_probe"] = {
        "preserve_content": {
            "result": "passed",
            "input_fingerprint": state["input_fingerprint"],
            "recorded": "2026-07-31T10:00:00Z",
            "observation": "Legacy evidence lacks its report origin.",
            "probe_fingerprint": f"sha256:{'2' * 64}",
        }
    }
    state_path = tmp_path / "legacy.state.yaml"
    state_path.write_text(yaml.safe_dump(state, sort_keys=False))

    loaded, diagnostics = load_state(state_path)

    assert loaded is None
    assert {item.code for item in diagnostics} == {"schema"}
    assert any("report_id" in item.message for item in diagnostics)


def test_state_loader_rejects_implementation_flag_report_mismatch(
    tmp_path: Path,
) -> None:
    state = yaml.safe_load((
        ROOT
        / "examples/product-repository/.pml/state/domains/notes/features/creation.state.yaml"
    ).read_text())
    obligation = "domains.notes.features.creation.rules.preserve_content"
    state["obligations"][obligation]["implemented"] = "implemented"
    state["obligations"][obligation]["implementation"] = {
        "status": "missing",
        "observation": "The accepted report found the behavior missing.",
        **EVIDENCE_ORIGIN,
        "recorded": "2026-08-02T12:00:00Z",
    }
    state_path = tmp_path / "mismatched.state.yaml"
    state_path.write_text(yaml.safe_dump(state, sort_keys=False))

    loaded, diagnostics = load_state(state_path)

    assert loaded is None
    assert [item.code for item in diagnostics] == ["implementation-mismatch"]


def test_lock_requires_an_independent_bindings_digest() -> None:
    schema = json.loads((ROOT / "schema" / "pml-lock.schema.json").read_text())
    lock = yaml.safe_load(
        (ROOT / "examples" / "product-repository" / ".pml" / "pml.lock").read_text()
    )
    assert list(Draft202012Validator(schema).iter_errors(lock)) == []

    del lock["bindings"]
    missing = list(Draft202012Validator(schema).iter_errors(lock))
    assert any("'bindings' is a required property" in error.message for error in missing)

    lock["bindings"] = {"digest": f"sha256:{'A' * 64}"}
    invalid = list(Draft202012Validator(schema).iter_errors(lock))
    assert [list(error.absolute_path) for error in invalid] == [["bindings", "digest"]]


def test_bindings_conformance_examples_are_validated_semantically() -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None

    bindings, diagnostics = load_bindings(
        ROOT / "examples" / "bindings.yaml", definition
    )
    assert bindings is not None
    assert diagnostics == []

    invalid_schema, schema_diagnostics = load_bindings(
        ROOT / "examples" / "invalid-bindings-schema.yaml", definition
    )
    assert invalid_schema is None
    assert {item.code for item in schema_diagnostics} == {"schema"}

    invalid_reference, reference_diagnostics = load_bindings(
        ROOT / "examples" / "invalid-bindings-reference.yaml", definition
    )
    assert invalid_reference is None
    assert {item.code for item in reference_diagnostics} == {
        "missing-verification-plan",
        "undefined-reference",
    }


def test_wrong_and_missing_lock_digests_stop_state_validation(tmp_path: Path) -> None:
    manifest, product = copy_example_layout(tmp_path)
    definition, _ = load_document(manifest)
    assert definition is not None
    lock_path = product / ".pml" / "pml.lock"
    shutil.copy(
        manifest.parent / "invalid-lock-wrong-bindings-digest.yaml",
        lock_path,
    )
    lock = yaml.safe_load(lock_path.read_text())

    lock["definition"]["digest"] = f"sha256:{'0' * 64}"
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False))
    diagnostics = validate_product_state(
        product, definition, definition_source=manifest
    )
    assert {item.code for item in diagnostics} == {
        "bindings-digest",
        "definition-digest",
    }

    shutil.copy(
        manifest.parent / "invalid-lock-missing-bindings-digest.yaml",
        lock_path,
    )
    missing = validate_product_state(
        product, definition, definition_source=manifest
    )
    assert {item.code for item in missing} == {"schema"}


def test_bound_paths_remain_relative_to_product_repository(tmp_path: Path) -> None:
    manifest, product = copy_example_layout(tmp_path)
    definition, _ = load_document(manifest)
    assert definition is not None
    owner_relative = manifest.parent / "src" / "notes.txt"
    owner_relative.parent.mkdir()
    owner_relative.write_text("owner source with the same relative path\n")

    assert input_fingerprint(product, ["src/notes.txt"]) != input_fingerprint(
        manifest.parent, ["src/notes.txt"]
    )
    assert validate_product_state(
        product, definition, definition_source=manifest
    ) == []


def test_probe_validation_rejects_invalid_lock_resolved_bindings(
    tmp_path: Path,
) -> None:
    manifest, product = copy_example_layout(tmp_path)
    definition, _ = load_document(manifest)
    assert definition is not None
    bindings_path = manifest.parent / "bindings.yaml"
    bindings = yaml.safe_load(bindings_path.read_text())
    bindings["invented_policy"] = True
    bindings_path.write_text(yaml.safe_dump(bindings, sort_keys=False))

    diagnostics = validate_probe_evidence(
        product, definition, {}, definition_source=manifest
    )
    assert {item.code for item in diagnostics} == {"schema"}


def test_product_local_bindings_do_not_override_owner_policy(tmp_path: Path) -> None:
    manifest, product = copy_example_layout(tmp_path)
    definition, _ = load_document(manifest)
    assert definition is not None
    (product / ".pml" / "bindings.yaml").write_text("[")

    assert validate_product_state(
        product, definition, definition_source=manifest
    ) == []


def test_product_cannot_redirect_bindings_away_from_passed_definition(
    tmp_path: Path, capsys
) -> None:
    manifest, product = copy_example_layout(tmp_path)
    definition, _ = load_document(manifest)
    assert definition is not None
    missing_source = validate_product_state(product, definition)
    assert {item.code for item in missing_source} == {"definition-source"}

    redirected_source = product / "policy"
    redirected_source.mkdir()
    shutil.copy(manifest, redirected_source / "minimal.pml.yaml")
    bindings = yaml.safe_load((manifest.parent / "bindings.yaml").read_text())
    rule_plan = bindings["bindings"]["domains.notes.features.creation"][
        "verification"
    ]["domains.notes.features.creation.rules.preserve_content"]
    rule_plan.clear()
    rule_plan["agent_judgment"] = 1.0
    (redirected_source / "bindings.yaml").write_text(
        yaml.safe_dump(bindings, sort_keys=False)
    )
    lock_path = product / ".pml" / "pml.lock"
    lock = yaml.safe_load(lock_path.read_text())
    lock["definition"]["source"] = "policy/minimal.pml.yaml"
    lock["bindings"]["digest"] = bindings_digest(bindings)
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False))

    assert main(["check", str(manifest), str(product)]) == 1
    output = capsys.readouterr().out
    assert "[definition-source]" in output
    assert "does not identify the loaded approved definition" in output
    assert "PML STATE VALID" not in output


def test_status_rejects_a_mismatched_bindings_digest(
    tmp_path: Path, capsys
) -> None:
    manifest, product = copy_example_layout(tmp_path)
    lock_path = product / ".pml" / "pml.lock"
    lock = yaml.safe_load(lock_path.read_text())
    lock["bindings"]["digest"] = f"sha256:{'0' * 64}"
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False))

    assert main(["status", str(manifest), str(product)]) == 1
    output = capsys.readouterr().out
    assert "[bindings-digest]" in output
    assert "implementation=" not in output


def test_oversized_product_state_fails_validation_and_status(
    tmp_path: Path, capsys
) -> None:
    manifest, product = copy_example_layout(tmp_path)
    document, diagnostics = load_document(manifest)
    assert diagnostics == []
    assert document is not None
    state_path = (
        product
        / ".pml/state/domains/notes/features/creation.state.yaml"
    )
    state_path.write_bytes(b"x" * (MAX_STATE_FILE_BYTES + 1))

    diagnostics = validate_product_state(
        product, document, definition_source=manifest
    )
    assert [item.code for item in diagnostics] == ["state-size"]

    assert main(["status", str(manifest), str(product)]) == 1
    output = capsys.readouterr().out
    assert "[state-size]" in output
    assert f"{MAX_STATE_FILE_BYTES}-byte tooling limit" in output
    assert "implementation=" not in output


def test_state_size_limit_is_checked_before_yaml_parsing(
    tmp_path: Path, monkeypatch
) -> None:
    state_path = tmp_path / "oversized.state.yaml"
    state_path.write_bytes(b"x" * (MAX_STATE_FILE_BYTES + 1))

    def unexpected_parse(*args, **kwargs):
        raise AssertionError("oversized state must not reach the YAML parser")

    monkeypatch.setattr("pml.project_state.yaml.load", unexpected_parse)
    state, diagnostics = load_state(state_path)

    assert state is None
    assert [item.code for item in diagnostics] == ["state-size"]


def test_product_state_limits_discovered_generated_state_files(
    tmp_path: Path, monkeypatch
) -> None:
    manifest, product = copy_example_layout(tmp_path)
    document, diagnostics = load_document(manifest)
    assert diagnostics == []
    assert document is not None
    state_root = product / ".pml" / "state"
    overflow = state_root / "overflow"
    overflow.mkdir()
    for index in range(MAX_PRODUCT_STATE_ENTRIES + 1):
        (overflow / f"unexpected_{index}.state.yaml").write_text("not state\n")

    loaded: list[Path] = []

    def record_load(path: Path) -> tuple[None, list]:
        loaded.append(path)
        return None, []

    monkeypatch.setattr("pml.project_state.load_product_state", lambda _, path: record_load(path))
    diagnostics = validate_product_state(
        product, document, definition_source=manifest
    )

    assert len(loaded) == min(MAX_PRODUCT_STATE_ENTRIES, 2)
    assert [item.code for item in diagnostics] == ["state-limit"]


def test_product_state_limits_non_state_recursive_traversal(tmp_path: Path) -> None:
    manifest, product = copy_example_layout(tmp_path)
    document, diagnostics = load_document(manifest)
    assert diagnostics == []
    assert document is not None
    non_state = product / ".pml" / "state" / "non_state"
    non_state.mkdir()
    for index in range(MAX_PRODUCT_STATE_SCAN_ENTRIES + 1):
        (non_state / f"unexpected_{index}.txt").write_text("not state\n")

    diagnostics = validate_product_state(
        product, document, definition_source=manifest
    )

    assert [item.code for item in diagnostics] == ["state-limit"]


def test_input_fingerprint_streams_bound_file_content(tmp_path: Path, monkeypatch) -> None:
    bound = tmp_path / "bound.bin"
    bound.write_bytes(b"x" * (128 * 1024))

    def unexpected_read_bytes(self: Path) -> bytes:
        raise AssertionError("bound input must be fingerprinted in chunks")

    monkeypatch.setattr(Path, "read_bytes", unexpected_read_bytes)
    assert input_fingerprint(tmp_path, ["bound.bin"]).startswith("sha256:")


def test_approved_bindings_change_makes_existing_evidence_stale(
    tmp_path: Path,
) -> None:
    manifest, product = copy_example_layout(tmp_path)
    definition, _ = load_document(manifest)
    assert definition is not None
    state_path = (
        product
        / ".pml/state/domains/notes/features/creation.state.yaml"
    )
    state = yaml.safe_load(state_path.read_text())
    obligation_id = "domains.notes.features.creation.rules.preserve_content"
    state["obligations"][obligation_id]["evidence"]["deterministic_probe"] = {
        "preserve_content": {
            "result": "passed",
            "input_fingerprint": state["input_fingerprint"],
            "recorded": "2026-07-31T10:00:00Z",
            "observation": "Probe passed under the prior policy.",
            **EVIDENCE_ORIGIN,
            "probe": "preserve_content",
            "probe_fingerprint": f"sha256:{'2' * 64}",
        }
    }
    state_path.write_text(yaml.safe_dump(state, sort_keys=False))

    bindings_path = manifest.parent / "bindings.yaml"
    bindings = yaml.safe_load(bindings_path.read_text())
    plan = bindings["bindings"]["domains.notes.features.creation"][
        "verification"
    ][obligation_id]
    plan["probes"]["preserve_content"] = 0.5
    plan["agent_judgment"] = 0.5
    bindings_path.write_text(yaml.safe_dump(bindings, sort_keys=False))
    lock_path = product / ".pml" / "pml.lock"
    lock = yaml.safe_load(lock_path.read_text())
    lock["bindings"]["digest"] = bindings_digest(bindings)
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False))

    diagnostics = validate_product_state(
        product, definition, definition_source=manifest
    )
    assert {item.code for item in diagnostics} == {"bindings-mismatch"}
    statuses = product_status(
        product, definition, definition_source=manifest
    )
    preserve_status = next(
        item
        for node in statuses
        for item in node.obligations
        if item.obligation_id == obligation_id
    )
    assert (preserve_status.signal, preserve_status.verified_coverage) == (
        "STALE",
        0,
    )


def test_rejects_unknown_related_node(tmp_path: Path) -> None:
    source = (ROOT / "examples" / "minimal.pml.yaml").read_text().replace(
        "        rules:\n",
        "        related_to: [domains.missing.features.unknown]\n        rules:\n",
        1,
    )
    manifest = tmp_path / "dependency.yaml"
    manifest.write_text(source)
    from pml.validator import validate_file

    assert any(item.code == "undefined-reference" and "unknown node" in item.message for item in validate_file(manifest))


def test_coverage_moves_from_stale_to_partial_to_verified() -> None:
    obligation = Obligation(
        id="domains.core.features.sample.rules.behavior",
        node_id="domains.core.features.sample",
        section="rules",
        local_id="behavior",
        definition={"statement": "THE SYSTEM MUST behave."},
    )
    current = f"sha256:{'a' * 64}"
    old = f"sha256:{'b' * 64}"
    common = {
        "result": "passed",
        "recorded": "2026-07-22T10:00:00Z",
        "observation": "Observed.",
    }
    state = {
        "evidence": {
            "deterministic_probe": {"probe": {**common, "input_fingerprint": old}},
            "agent_judgment": {**common, "input_fingerprint": old},
        }
    }
    plan = {"probes": {"probe": 0.5}, "agent_judgment": 0.5}
    stale = derive_obligation_status(obligation, state, current, True, plan)
    assert (stale.signal, stale.verified_coverage) == ("STALE", 0)

    state["evidence"]["deterministic_probe"]["probe"]["input_fingerprint"] = current
    partial = derive_obligation_status(obligation, state, current, True, plan)
    assert (partial.signal, partial.verified_coverage) == ("PARTIAL", 0.5)

    state["evidence"]["agent_judgment"]["input_fingerprint"] = current
    verified = derive_obligation_status(obligation, state, current, True, plan)
    assert (verified.signal, verified.verified_coverage) == ("VERIFIED", 1.0)


def test_binding_coverage_must_total_one(tmp_path: Path) -> None:
    document, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert document is not None
    node_id = "domains.notes.features.creation"
    product = tmp_path / "product"
    owner = tmp_path / "product-pml"
    owner.mkdir()
    (owner / "minimal.pml.yaml").write_text(
        (ROOT / "examples" / "minimal.pml.yaml").read_text()
    )
    metadata = product / ".pml"
    metadata.mkdir(parents=True)
    bindings_text = (
        "pml_bindings: '0.1'\nbindings:\n"
        f"  {node_id}:\n"
        "    paths: [src]\n"
        "    verification:\n"
        f"      {node_id}.rules.preserve_content:\n"
        "        probes: {preserve: 0.5}\n"
        "        agent_judgment: 0.4\n"
        f"      {node_id}.use_cases.create_note:\n"
        "        agent_judgment: 1.0\n"
    )
    (owner / "bindings.yaml").write_text(bindings_text)
    bindings = yaml.safe_load(bindings_text)
    (metadata / "pml.lock").write_text(yaml.safe_dump({
        "pml_lock": "0.1",
        "definition": {
            "source": "../product-pml/minimal.pml.yaml",
            "revision": "approved",
            "digest": canonical_hash(document),
        },
        "bindings": {"digest": bindings_digest(bindings)},
    }, sort_keys=False))
    diagnostics = validate_product_state(
        product,
        document,
        definition_source=owner / "minimal.pml.yaml",
    )
    assert any(item.code == "coverage-total" for item in diagnostics)


def test_project_and_domain_rules_are_obligations() -> None:
    document, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert document is not None
    document["rules"] = {
        "global": {"statement": "THE SYSTEM MUST preserve product truth."}
    }
    document["domains"]["notes"]["rules"] = {
        "domain": {"statement": "Notes MUST remain durable."}
    }
    ids = {item.id for item in enumerate_obligations(document)}
    assert "project.rules.global" in ids
    assert "domains.notes.rules.domain" in ids


def test_architecture_constraints_have_separate_state_and_derivation(tmp_path: Path) -> None:
    source = (ROOT / "examples" / "minimal.pml.yaml").read_text().replace(
        "domains:\n",
        """architecture:
  approved_runtime:
    category: runtime
    selection: Approved runtime.
    rationale: Owner approval is required to replace this runtime.
    constraints:
      portable_execution:
        statement: The runtime MUST preserve portable execution.
domains:
""",
        1,
    ).replace("        actors:\n", "        architecture: [approved_runtime]\n        actors:\n", 1)
    manifest = tmp_path / "architecture.pml.yaml"
    manifest.write_text(source)
    document, diagnostics = load_document(manifest)
    assert diagnostics == []
    assert document is not None
    decision = document["architecture"]["approved_runtime"]
    obligation = next(enumerate_architecture_obligations(document))
    architecture_bindings = {
        "approved_runtime": {
            "paths": ["runtime"],
            "verification": {obligation.id: {"agent_judgment": 1.0}},
        }
    }
    product, approved_manifest, digest = write_architecture_layout(
        tmp_path, document, architecture_bindings
    )
    metadata = product / ".pml"
    architecture_dir = metadata / "architecture"
    architecture_dir.mkdir()
    source_path = product / "runtime" / "selection"
    source_path.parent.mkdir()
    source_path.write_text("approved\n")
    state = {
        "pml_state": "0.1",
        "node": "architecture.approved_runtime",
        "definition_hash": canonical_hash(decision),
        "bindings_digest": digest,
        "input_fingerprint": input_fingerprint(product, ["runtime"]),
        "obligations": {obligation.id: {"implemented": "implemented", "evidence": {}}},
    }
    (architecture_dir / "approved_runtime.state.yaml").write_text(yaml.safe_dump(state, sort_keys=False))
    assert validate_architecture_state(
        product, document, definition_source=approved_manifest
    ) == []
    status = architecture_status(
        product, document, definition_source=approved_manifest
    )
    assert [(item.node_id, item.verification_percent) for item in status] == [("architecture.approved_runtime", 0)]


def test_architecture_status_ignores_state_for_a_different_decision(
    tmp_path: Path,
) -> None:
    document, diagnostics = load_document(
        ROOT / "examples" / "architecture-decisions.pml.yaml"
    )
    assert diagnostics == []
    assert document is not None
    obligation = next(enumerate_architecture_obligations(document))
    product, manifest, digest = write_architecture_layout(tmp_path, document, {
        "durable_store": {
            "paths": ["runtime"],
            "verification": {obligation.id: {"agent_judgment": 1.0}},
        }
    })
    runtime = product / "runtime"
    runtime.mkdir()
    (runtime / "selection").write_text("approved\n")
    architecture = product / ".pml" / "architecture"
    architecture.mkdir()
    current_input = input_fingerprint(product, ["runtime"])
    state = {
        "pml_state": "0.1",
        "node": "architecture.other_decision",
        "definition_hash": canonical_hash(document["architecture"]["durable_store"]),
        "bindings_digest": digest,
        "input_fingerprint": current_input,
        "obligations": {
            obligation.id: {
                "implemented": "implemented",
                "evidence": {
                    "agent_judgment": {
                        "result": "passed",
                        "input_fingerprint": current_input,
                        "recorded": "2026-08-02T00:00:00Z",
                        "observation": "The constraint holds.",
                        **EVIDENCE_ORIGIN,
                        "reproduction": ["Run the approved check."],
                    }
                },
            }
        },
    }
    (architecture / "durable_store.state.yaml").write_text(
        yaml.safe_dump(state, sort_keys=False)
    )
    status_diagnostics: list = []

    status = architecture_status(
        product,
        document,
        definition_source=manifest,
        state_diagnostics=status_diagnostics,
    )

    assert status[0].obligations[0].signal == "UNVERIFIED"
    assert any(item.code == "state-path" for item in status_diagnostics)


def test_architecture_state_rejects_duplicate_and_nested_state_paths(
    tmp_path: Path,
    capsys,
) -> None:
    document, diagnostics = load_document(
        ROOT / "examples" / "architecture-decisions.pml.yaml"
    )
    assert diagnostics == []
    assert document is not None
    obligation = next(enumerate_architecture_obligations(document))
    product, manifest, digest = write_architecture_layout(tmp_path, document, {
        "durable_store": {
            "paths": ["runtime"],
            "verification": {obligation.id: {"agent_judgment": 1.0}},
        }
    })
    (product / "runtime").mkdir()
    architecture = product / ".pml" / "architecture"
    architecture.mkdir()
    state = {
        "pml_state": "0.1",
        "node": "architecture.durable_store",
        "definition_hash": canonical_hash(
            document["architecture"]["durable_store"]
        ),
        "bindings_digest": digest,
        "input_fingerprint": input_fingerprint(product, ["runtime"]),
        "obligations": {
            obligation.id: {"implemented": "unknown", "evidence": {}}
        },
    }
    state_text = yaml.safe_dump(state, sort_keys=False)
    (architecture / "durable_store.state.yaml").write_text(state_text)
    (architecture / "duplicate.state.yaml").write_text(state_text)
    nested = architecture / "nested"
    nested.mkdir()
    (nested / "stray.state.yaml").write_text(state_text)

    state_path_errors = [
        item
        for item in validate_architecture_state(
            product, document, definition_source=manifest
        )
        if item.code == "state-path"
    ]
    assert {Path(item.path).name for item in state_path_errors} == {
        "duplicate.state.yaml",
        "nested",
    }
    assert main(["check", str(manifest), str(product)]) == 1
    check_output = capsys.readouterr().out
    assert "duplicate.state.yaml: [state-path]" in check_output
    assert "nested: [state-path]" in check_output


def test_architecture_state_limits_candidate_files(tmp_path: Path) -> None:
    document, diagnostics = load_document(
        ROOT / "examples" / "architecture-decisions.pml.yaml"
    )
    assert diagnostics == []
    assert document is not None
    obligation = next(enumerate_architecture_obligations(document))
    product, manifest, digest = write_architecture_layout(tmp_path, document, {
        "durable_store": {
            "paths": ["runtime"],
            "verification": {obligation.id: {"agent_judgment": 1.0}},
        }
    })
    (product / "runtime").mkdir()
    architecture = product / ".pml" / "architecture"
    architecture.mkdir()
    state = {
        "pml_state": "0.1",
        "node": "architecture.durable_store",
        "definition_hash": canonical_hash(document["architecture"]["durable_store"]),
        "bindings_digest": digest,
        "input_fingerprint": input_fingerprint(product, ["runtime"]),
        "obligations": {obligation.id: {"implemented": "unknown", "evidence": {}}},
    }
    for index in range(3):
        (architecture / f"candidate_{index}.state.yaml").write_text(
            yaml.safe_dump(state, sort_keys=False)
        )

    diagnostics = validate_architecture_state(
        product, document, definition_source=manifest
    )

    assert any(item.code == "state-limit" for item in diagnostics)


def test_oversized_architecture_state_fails_validation_and_status(
    tmp_path: Path, capsys
) -> None:
    document, diagnostics = load_document(
        ROOT / "examples" / "architecture-decisions.pml.yaml"
    )
    assert diagnostics == []
    assert document is not None
    obligation = next(enumerate_architecture_obligations(document))
    product, manifest, _ = write_architecture_layout(tmp_path, document, {
        "durable_store": {
            "paths": ["runtime"],
            "verification": {obligation.id: {"agent_judgment": 1.0}},
        }
    })
    (product / "runtime").mkdir()
    architecture = product / ".pml" / "architecture"
    architecture.mkdir()
    state_path = architecture / "durable_store.state.yaml"
    state_path.write_bytes(b"x" * (MAX_STATE_FILE_BYTES + 1))

    diagnostics = validate_architecture_state(
        product, document, definition_source=manifest
    )
    assert [item.code for item in diagnostics] == ["state-size"]

    assert main([
        "architecture-status",
        str(manifest),
        str(product),
    ]) == 1
    output = capsys.readouterr().out
    assert "[state-size]" in output
    assert f"{MAX_STATE_FILE_BYTES}-byte tooling limit" in output
    assert "implementation=" not in output


def test_architecture_state_limits_non_state_entries(tmp_path: Path) -> None:
    document, diagnostics = load_document(
        ROOT / "examples" / "architecture-decisions.pml.yaml"
    )
    assert diagnostics == []
    assert document is not None
    product, manifest, _ = write_architecture_layout(tmp_path, document, {
        "durable_store": {
            "paths": ["runtime"],
            "verification": {
                "architecture.durable_store.constraints.preserve_committed_records": {
                    "agent_judgment": 1.0
                }
            },
        }
    })
    architecture = product / ".pml" / "architecture"
    architecture.mkdir()
    for index in range(MAX_ARCHITECTURE_STATE_ENTRIES + 1):
        (architecture / f"unexpected_{index}").write_text("not state\n")

    diagnostics = validate_architecture_state(
        product, document, definition_source=manifest
    )

    assert sum(item.code == "state-path" for item in diagnostics) == (
        MAX_ARCHITECTURE_STATE_ENTRIES
    )
    assert any(item.code == "state-limit" for item in diagnostics)


def test_architecture_state_root_rejects_symlink_outside_product_repository(
    tmp_path: Path,
) -> None:
    document, diagnostics = load_document(
        ROOT / "examples" / "architecture-decisions.pml.yaml"
    )
    assert diagnostics == []
    assert document is not None
    obligation = next(enumerate_architecture_obligations(document))
    product, manifest, _ = write_architecture_layout(tmp_path, document, {
        "durable_store": {
            "paths": ["runtime"],
            "verification": {obligation.id: {"agent_judgment": 1.0}},
        }
    })
    external = tmp_path / "external"
    external.mkdir()
    (product / ".pml" / "architecture").symlink_to(
        external, target_is_directory=True
    )

    diagnostics = validate_architecture_state(
        product, document, definition_source=manifest
    )

    assert [item.code for item in diagnostics] == ["state-path"]
    assert list(external.iterdir()) == []


def test_product_state_root_rejects_symlink_outside_product_repository(
    tmp_path: Path,
) -> None:
    manifest, product = copy_example_layout(tmp_path)
    document, diagnostics = load_document(manifest)
    assert diagnostics == []
    assert document is not None
    external = tmp_path / "external"
    external.mkdir()
    state_root = product / ".pml" / "state"
    shutil.rmtree(state_root)
    state_root.symlink_to(external, target_is_directory=True)

    diagnostics = validate_product_state(
        product, document, definition_source=manifest
    )

    assert [item.code for item in diagnostics] == ["state-path"]
    assert list(external.iterdir()) == []


def test_product_state_write_stays_in_pinned_directory_after_symlink_swap(
    tmp_path: Path, monkeypatch
) -> None:
    product = tmp_path / "product"
    state_path = (
        product / ".pml/state/domains/notes/features/creation.state.yaml"
    )
    state_path.parent.mkdir(parents=True)
    external = tmp_path / "external"
    external_state = external / "notes/features/creation.state.yaml"
    external_state.parent.mkdir(parents=True)
    external_state.write_bytes(b"external state")
    original_domains = product / "original-domains"
    original_open = os.open

    def swap_before_state_open(path, flags, mode=0o777, *, dir_fd=None):
        if path == "creation.state.yaml" and flags & os.O_CREAT:
            (product / ".pml/state/domains").rename(original_domains)
            (product / ".pml/state/domains").symlink_to(
                external, target_is_directory=True
            )
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr("pml.project_state.os.open", swap_before_state_open)

    assert write_product_state(product, state_path, b"pinned state") == []
    assert external_state.read_bytes() == b"external state"
    assert (
        original_domains / "notes/features/creation.state.yaml"
    ).read_bytes() == b"pinned state"


def test_architecture_state_write_stays_in_pinned_directory_after_symlink_swap(
    tmp_path: Path, monkeypatch
) -> None:
    product = tmp_path / "product"
    state_path = product / ".pml/architecture/durable_store.state.yaml"
    state_path.parent.mkdir(parents=True)
    external = tmp_path / "external"
    external_state = external / "durable_store.state.yaml"
    external.mkdir()
    external_state.write_bytes(b"external state")
    original_architecture = product / "original-architecture"
    original_open = os.open

    def swap_before_state_open(path, flags, mode=0o777, *, dir_fd=None):
        if path == "durable_store.state.yaml" and flags & os.O_CREAT:
            (product / ".pml/architecture").rename(original_architecture)
            (product / ".pml/architecture").symlink_to(
                external, target_is_directory=True
            )
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr("pml.project_state.os.open", swap_before_state_open)

    assert write_architecture_state(product, state_path, b"pinned state") == []
    assert external_state.read_bytes() == b"external state"
    assert (
        original_architecture / "durable_store.state.yaml"
    ).read_bytes() == b"pinned state"


def test_product_state_scan_closes_queued_descriptors_on_limit(
    tmp_path: Path, monkeypatch
) -> None:
    manifest, product = copy_example_layout(tmp_path)
    document, diagnostics = load_document(manifest)
    assert diagnostics == []
    assert document is not None
    state_root = product / ".pml" / "state"
    for index in range(MAX_PRODUCT_STATE_SCAN_ENTRIES):
        (state_root / f"directory_{index}").mkdir()
    opened: list[int] = []
    closed: list[int] = []
    original_open = os.open
    original_close = os.close

    def record_open(path, flags, mode=0o777, *, dir_fd=None):
        fd = original_open(path, flags, mode, dir_fd=dir_fd)
        opened.append(fd)
        return fd

    def record_close(fd):
        closed.append(fd)
        original_close(fd)

    monkeypatch.setattr("pml.project_state.os.open", record_open)
    monkeypatch.setattr("pml.project_state.os.close", record_close)

    diagnostics = validate_product_state(
        product, document, definition_source=manifest
    )

    assert any(item.code == "state-limit" for item in diagnostics)
    assert all(fd in closed for fd in opened[3:])


def test_probe_evidence_rejects_architecture_state_root_symlink(
    tmp_path: Path,
) -> None:
    document, diagnostics = load_document(
        ROOT / "examples" / "architecture-decisions.pml.yaml"
    )
    assert diagnostics == []
    assert document is not None
    obligation = next(enumerate_architecture_obligations(document))
    product, manifest, _ = write_architecture_layout(tmp_path, document, {
        "durable_store": {
            "paths": ["runtime"],
            "verification": {obligation.id: {"agent_judgment": 1.0}},
        }
    })
    external = tmp_path / "external"
    external.mkdir()
    (product / ".pml" / "architecture").symlink_to(
        external, target_is_directory=True
    )

    diagnostics = validate_probe_evidence(
        product, document, {}, definition_source=manifest
    )

    assert [item.code for item in diagnostics] == ["state-path"]


def test_architecture_state_and_status_ignore_product_local_bindings(
    tmp_path: Path,
    capsys,
) -> None:
    document, diagnostics = load_document(
        ROOT / "examples" / "architecture-decisions.pml.yaml"
    )
    assert diagnostics == []
    assert document is not None
    obligation = next(enumerate_architecture_obligations(document))
    product, manifest, digest = write_architecture_layout(tmp_path, document, {
        "durable_store": {
            "paths": ["runtime"],
            "verification": {obligation.id: {"agent_judgment": 1.0}},
        }
    })
    (product / "runtime").mkdir()
    architecture = product / ".pml" / "architecture"
    architecture.mkdir()
    state = {
        "pml_state": "0.1",
        "node": "architecture.durable_store",
        "definition_hash": canonical_hash(
            document["architecture"]["durable_store"]
        ),
        "bindings_digest": digest,
        "input_fingerprint": input_fingerprint(product, ["runtime"]),
        "obligations": {
            obligation.id: {"implemented": "unknown", "evidence": {}}
        },
    }
    (architecture / "durable_store.state.yaml").write_text(
        yaml.safe_dump(state, sort_keys=False)
    )
    (product / ".pml" / "bindings.yaml").write_text("[")

    assert validate_architecture_state(
        product, document, definition_source=manifest
    ) == []
    assert main([
        "architecture-status",
        str(manifest),
        str(product),
    ]) == 0
    output = capsys.readouterr().out
    assert "architecture.durable_store implementation=0%" in output


def test_architecture_binding_rejects_noncanonical_current_directory_path(
    tmp_path: Path,
) -> None:
    document, diagnostics = load_document(
        ROOT / "examples" / "architecture-decisions.pml.yaml"
    )
    assert diagnostics == []
    assert document is not None
    obligation = "architecture.durable_store.constraints.preserve_committed_records"
    product, manifest, _ = write_architecture_layout(tmp_path, document, {
        "durable_store": {
            "paths": ["./"],
            "verification": {obligation: {"agent_judgment": 1.0}},
        }
    })

    diagnostics = validate_architecture_state(
        product, document, definition_source=manifest
    )

    assert any(item.code == "schema" and "'./' does not match" in item.message for item in diagnostics)


def test_architecture_status_makes_evidence_stale_after_decision_change(
    tmp_path: Path,
) -> None:
    document, diagnostics = load_document(
        ROOT / "examples" / "architecture-decisions.pml.yaml"
    )
    assert diagnostics == []
    assert document is not None
    decision = document["architecture"]["durable_store"]
    obligation = next(enumerate_architecture_obligations(document))
    bindings = {
        "pml_bindings": "0.1",
        "bindings": {},
        "architecture": {
            "durable_store": {
                "paths": ["runtime"],
                "verification": {obligation.id: {"agent_judgment": 1.0}},
            }
        },
    }
    product = tmp_path / "product"
    runtime = product / "runtime"
    runtime.mkdir(parents=True)
    metadata = product / ".pml" / "architecture"
    metadata.mkdir(parents=True)
    current_input = input_fingerprint(product, ["runtime"])
    state = {
        "pml_state": "0.1",
        "node": "architecture.durable_store",
        "definition_hash": canonical_hash(decision),
        "bindings_digest": bindings_digest(bindings),
        "input_fingerprint": current_input,
        "obligations": {
            obligation.id: {
                "implemented": "implemented",
                "evidence": {
                    "agent_judgment": {
                        "result": "passed",
                        "input_fingerprint": current_input,
                        "recorded": "2026-08-01T00:00:00Z",
                        "observation": "The approved constraint holds.",
                        **EVIDENCE_ORIGIN,
                        "reproduction": ["Run the approved check."],
                    }
                },
            }
        },
    }
    (metadata / "durable_store.state.yaml").write_text(
        yaml.safe_dump(state, sort_keys=False)
    )
    changed = yaml.safe_load(yaml.safe_dump(document))
    changed["architecture"]["durable_store"]["selection"] = "A changed store."
    locked_bindings = LockedBindings(
        bindings, tmp_path / "owner" / "bindings.yaml", bindings_digest(bindings)
    )

    status = architecture_status(product, changed, locked_bindings=locked_bindings)

    assert status[0].obligations[0].signal == "STALE"
    assert status[0].verification_percent == 0


def test_architecture_binding_rejects_symlink_outside_product_repository(tmp_path: Path) -> None:
    document, diagnostics = load_document(ROOT / "examples" / "architecture-decisions.pml.yaml")
    assert diagnostics == []
    assert document is not None
    obligation = "architecture.durable_store.constraints.preserve_committed_records"
    product, manifest, _ = write_architecture_layout(tmp_path, document, {
        "durable_store": {
            "paths": ["runtime"],
            "verification": {obligation: {"agent_judgment": 1.0}},
        }
    })
    external = tmp_path / "external"
    external.mkdir()
    (product / "runtime").symlink_to(external, target_is_directory=True)
    assert any(
        item.code == "outside-repository"
        for item in validate_architecture_state(
            product, document, definition_source=manifest
        )
    )


def test_architecture_binding_rejects_child_symlink_outside_product_repository(tmp_path: Path) -> None:
    document, diagnostics = load_document(ROOT / "examples" / "architecture-decisions.pml.yaml")
    assert diagnostics == []
    assert document is not None
    obligation = "architecture.durable_store.constraints.preserve_committed_records"
    product, manifest, _ = write_architecture_layout(tmp_path, document, {
        "durable_store": {
            "paths": ["runtime"],
            "verification": {obligation: {"agent_judgment": 1.0}},
        }
    })
    runtime = product / "runtime"
    runtime.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (external / "selection").write_text("outside\n")
    (runtime / "selection").symlink_to(external / "selection")
    diagnostics = validate_architecture_state(
        product, document, definition_source=manifest
    )
    assert any(item.code == "outside-repository" and "runtime/selection" in item.message for item in diagnostics)


def test_architecture_binding_limits_in_repository_boundary_scan(
    tmp_path: Path,
) -> None:
    document, diagnostics = load_document(
        ROOT / "examples" / "architecture-decisions.pml.yaml"
    )
    assert diagnostics == []
    assert document is not None
    obligation = "architecture.durable_store.constraints.preserve_committed_records"
    product, manifest, _ = write_architecture_layout(tmp_path, document, {
        "durable_store": {
            "paths": ["runtime"],
            "verification": {obligation: {"agent_judgment": 1.0}},
        }
    })
    runtime = product / "runtime"
    runtime.mkdir()
    for index in range(MAX_BOUNDARY_SCAN_ENTRIES + 1):
        (runtime / f"in_repository_{index}").write_text("ordinary input\n")

    diagnostics = validate_architecture_state(
        product, document, definition_source=manifest
    )

    assert any(item.code == "binding-scan-limit" for item in diagnostics)


def test_architecture_decision_without_constraints_requires_no_state_or_binding(tmp_path: Path) -> None:
    source = (ROOT / "examples" / "minimal.pml.yaml").read_text().replace(
        "domains:\n",
        """architecture:
  approved_runtime:
    category: runtime
    selection: Approved runtime.
    rationale: Owner approval is required to replace this runtime.
domains:
""",
        1,
    ).replace("        actors:\n", "        architecture: [approved_runtime]\n        actors:\n", 1)
    manifest = tmp_path / "unconstrained-architecture.pml.yaml"
    manifest.write_text(source)
    document, diagnostics = load_document(manifest)
    assert diagnostics == []
    assert document is not None
    product, approved_manifest, _ = write_architecture_layout(
        tmp_path, document, {}
    )
    assert validate_architecture_state(
        product, document, definition_source=approved_manifest
    ) == []
    assert architecture_status(
        product, document, definition_source=approved_manifest
    ) == []


def test_unconstrained_architecture_rejects_unresolved_binding_and_state(tmp_path: Path) -> None:
    source = (ROOT / "examples" / "minimal.pml.yaml").read_text().replace(
        "domains:\n",
        """architecture:
  approved_runtime:
    category: runtime
    selection: Approved runtime.
    rationale: Owner approval is required to replace this runtime.
domains:
""",
        1,
    ).replace("        actors:\n", "        architecture: [approved_runtime]\n        actors:\n", 1)
    manifest = tmp_path / "unconstrained-architecture.pml.yaml"
    manifest.write_text(source)
    document, diagnostics = load_document(manifest)
    assert diagnostics == []
    assert document is not None
    product, approved_manifest, digest = write_architecture_layout(
        tmp_path,
        document,
        {
            "invented": {
                "paths": ["runtime"],
                "verification": {},
            }
        },
    )
    metadata = product / ".pml"
    architecture = metadata / "architecture"
    architecture.mkdir()
    (product / "runtime").mkdir()
    (architecture / "invented.state.yaml").write_text("\n".join([
        "pml_state: '0.1'",
        "node: architecture.invented",
        f"definition_hash: sha256:{'a' * 64}",
        f"bindings_digest: {digest}",
        f"input_fingerprint: sha256:{'b' * 64}",
        "obligations: {}",
        "",
    ]))
    diagnostics = validate_architecture_state(
        product, document, definition_source=approved_manifest
    )
    assert sum(item.code == "undefined-reference" for item in diagnostics) == 2
