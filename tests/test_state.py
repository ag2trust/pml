from pathlib import Path
import shutil

import json
from jsonschema import Draft202012Validator
import yaml

from pml.obligations import Obligation, enumerate_architecture_obligations, enumerate_obligations
from pml.cli import main
from pml.project_state import (
    bindings_digest,
    canonical_hash,
    input_fingerprint,
    load_bindings,
    validate_architecture_state,
    validate_probe_evidence,
    validate_product_state,
)
from pml.status import architecture_status, derive_obligation_status, product_status
from pml.validator import load_document


ROOT = Path(__file__).resolve().parents[1]


def copy_example_layout(tmp_path: Path) -> tuple[Path, Path]:
    examples = tmp_path / "examples"
    shutil.copytree(ROOT / "examples", examples)
    return examples / "minimal.pml.yaml", examples / "product-repository"


def test_obligations_have_stable_ids() -> None:
    document, diagnostics = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert diagnostics == []
    assert document is not None
    obligations = list(enumerate_obligations(document))
    assert [item.id for item in obligations] == [
        "domains.notes.features.creation.rules.preserve_content",
        "domains.notes.features.creation.use_cases.create_note",
    ]


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
    metadata = tmp_path / ".pml"
    architecture_dir = metadata / "architecture"
    architecture_dir.mkdir(parents=True)
    source_path = tmp_path / "runtime" / "selection"
    source_path.parent.mkdir()
    source_path.write_text("approved\n")
    (metadata / "bindings.yaml").write_text("\n".join([
        "pml_bindings: '0.1'",
        "bindings: {}",
        "architecture:",
        "  approved_runtime:",
        "    paths: [runtime]",
        "    verification:",
        "      architecture.approved_runtime.constraints.portable_execution:",
        "        agent_judgment: 1.0",
        "",
    ]))
    state = {
        "pml_state": "0.1",
        "node": "architecture.approved_runtime",
        "definition_hash": canonical_hash(decision),
        "input_fingerprint": input_fingerprint(tmp_path, ["runtime"]),
        "obligations": {obligation.id: {"implemented": "implemented", "evidence": {}}},
    }
    (architecture_dir / "approved_runtime.state.yaml").write_text(yaml.safe_dump(state, sort_keys=False))
    assert validate_architecture_state(tmp_path, document) == []
    status = architecture_status(tmp_path, document)
    assert [(item.node_id, item.verification_percent) for item in status] == [("architecture.approved_runtime", 0)]


def test_architecture_binding_rejects_symlink_outside_product_repository(tmp_path: Path) -> None:
    document, diagnostics = load_document(ROOT / "examples" / "architecture-decisions.pml.yaml")
    assert diagnostics == []
    assert document is not None
    product = tmp_path / "product"
    metadata = product / ".pml"
    metadata.mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    (product / "runtime").symlink_to(external, target_is_directory=True)
    (metadata / "bindings.yaml").write_text("\n".join([
        "pml_bindings: '0.1'",
        "bindings: {}",
        "architecture:",
        "  durable_store:",
        "    paths: [runtime]",
        "    verification:",
        "      architecture.durable_store.constraints.preserve_committed_records:",
        "        agent_judgment: 1.0",
        "",
    ]))
    assert any(item.code == "outside-repository" for item in validate_architecture_state(product, document))
