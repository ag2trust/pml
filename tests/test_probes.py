import json
import os
from pathlib import Path
import shutil

from jsonschema import Draft202012Validator
import pytest
import yaml

from pml.cli import main
from pml.probes import (
    MAX_PROBE_DISCOVERY_ENTRIES,
    MAX_PROBE_FILES,
    MAX_PROBE_FILE_BYTES,
    load_probes,
    missing_probe_diagnostics,
    probe_fingerprint,
)
from pml.validator import load_document


ROOT = Path(__file__).resolve().parents[1]


def product_copy(tmp_path: Path) -> Path:
    owner_source = tmp_path / "product-pml"
    owner_source.mkdir()
    shutil.copy(ROOT / "examples" / "minimal.pml.yaml", owner_source)
    shutil.copy(ROOT / "examples" / "bindings.yaml", owner_source)
    product = tmp_path / "product"
    shutil.copytree(ROOT / "examples" / "product-repository", product)
    lock_path = product / ".pml" / "pml.lock"
    lock = yaml.safe_load(lock_path.read_text())
    lock["definition"]["source"] = "../product-pml/minimal.pml.yaml"
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False))
    return product


def owner_definition_path(product: Path) -> Path:
    return product.parent / "product-pml" / "minimal.pml.yaml"


def write_preserve_content_probe(path: Path) -> None:
    path.write_text(
        """\
pml_probe: "0.1"
probe: preserve_content
verifies: domains.notes.features.creation.rules.preserve_content
env: staging
steps:
  - cli: [notes, verify-content]
    as: member
    expect: {exit: 0}
"""
    )


def write_probe(
    path: Path,
    probe_id: str,
    *,
    steps: int = 1,
    verifies: str = "domains.notes.features.creation.rules.preserve_content",
) -> None:
    steps_text = "  - session: reset\n" * steps
    path.write_text(
        f"""\
pml_probe: "0.1"
probe: {probe_id}
verifies: {verifies}
env: staging
steps:
{steps_text}"""
    )


def minimal_definition() -> dict:
    definition, diagnostics = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert diagnostics == []
    assert definition is not None
    return definition


def test_probe_schema_is_a_valid_metaschema_document() -> None:
    schema = json.loads((ROOT / "schema" / "pml-probe.schema.json").read_text())

    Draft202012Validator.check_schema(schema)


def test_approved_probe_is_valid_and_bound_to_obligation() -> None:
    definition, diagnostics = load_document(ROOT / "examples" / "assistant-creation.pml.yaml")
    assert diagnostics == []
    assert definition is not None

    probes, probe_diagnostics = load_probes(ROOT / "examples" / "assistant-persistence.probe.yaml", definition)

    assert probe_diagnostics == []
    assert probes["assistant_config_persistence"]["verifies"].endswith("behaviors.assistant_creation.outcome")
    assert probe_fingerprint(probes["assistant_config_persistence"]).startswith("sha256:")


def test_architecture_constraint_probe_is_valid_and_complete(tmp_path: Path) -> None:
    definition, diagnostics = load_document(ROOT / "examples" / "architecture-decisions.pml.yaml")
    assert diagnostics == []
    assert definition is not None
    obligation = "architecture.durable_store.constraints.preserve_committed_records"
    bindings = {
        "bindings": {},
        "architecture": {
            "durable_store": {
                "verification": {obligation: {"probes": {"durable_store": 1.0}}}
            }
        },
    }
    probe = tmp_path / "durable-store.probe.yaml"
    probe.write_text(
        f"""\
pml_probe: "0.1"
probe: durable_store
verifies: {obligation}
env: staging
steps:
  - cli: [records, verify-preservation]
    expect: {{exit: 0}}
"""
    )
    probes, probe_diagnostics = load_probes(probe, definition, bindings)
    assert probe_diagnostics == []
    assert missing_probe_diagnostics(probes, definition, bindings) == []


def test_probes_can_target_behavior_transition_obligations(
    tmp_path: Path, capsys
) -> None:
    definition, diagnostics = load_document(
        ROOT / "examples" / "behavior-one-of-output.pml.yaml"
    )
    assert diagnostics == []
    assert definition is not None
    behavior_id = (
        "domains.email.features.triage.behaviors.importance_decision"
    )
    targets = [
        f"{behavior_id}.outcome",
        f"{behavior_id}.failures.processing_failure",
    ]

    for index, target in enumerate(targets):
        probe_path = tmp_path / f"transition-{index}.probe.yaml"
        probe_path.write_text(
            f"""\
pml_probe: "0.1"
probe: transition_{index}
verifies: {target}
env: staging
steps:
  - cli: [email, verify-transition]
    expect: {{exit: 0}}
"""
        )

        probes, probe_diagnostics = load_probes(probe_path, definition)

        assert list(probes) == [f"transition_{index}"]
        assert probe_diagnostics == []

    completion_path = tmp_path / "completion.probe.yaml"
    completion_path.write_text(
        f"""\
pml_probe: "0.1"
probe: completion
verifies: {behavior_id}.completion
env: staging
steps:
  - cli: [email, verify-transition]
    expect: {{exit: 0}}
"""
    )
    completion_probes, completion_diagnostics = load_probes(completion_path, definition)
    assert list(completion_probes) == ["completion"]
    assert [(item.code, item.message) for item in completion_diagnostics] == [
        (
            "PML-E-PROBE-INELIGIBLE",
            "deterministic probes cannot verify completion obligations; "
            "see docs/verification.md#deterministic-probe-eligibility",
        )
    ]
    assert main([
        "validate-probes",
        str(ROOT / "examples" / "behavior-one-of-output.pml.yaml"),
        str(completion_path),
    ]) == 1
    assert "[PML-E-PROBE-INELIGIBLE]" in capsys.readouterr().out

    legacy_path = tmp_path / "legacy-component.probe.yaml"
    legacy_path.write_text(
        (tmp_path / "transition-0.probe.yaml").read_text().replace(
            ".behaviors.", ".components."
        )
    )
    legacy_probes, legacy_diagnostics = load_probes(legacy_path, definition)
    assert legacy_probes == {}
    assert {item.code for item in legacy_diagnostics} == {"schema"}


def test_probe_rejects_unknown_actor_and_forward_variable(tmp_path: Path) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    probe = tmp_path / "invalid.probe.yaml"
    probe.write_text(
        """\
pml_probe: "0.1"
probe: invalid
verifies: domains.notes.features.creation.rules.preserve_content
env: staging
steps:
  - http: GET /notes/{note_id}
    as: stranger
    expect: {status: 200}
"""
    )

    _, diagnostics = load_probes(probe, definition)

    assert {item.code for item in diagnostics} == {"undefined-variable", "undefined-reference"}


def test_complete_probes_are_defined_by_product_bindings(tmp_path: Path) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    obligation_id = "domains.notes.features.creation.rules.preserve_content"
    bindings = {
        "bindings": {
            "domains.notes.features.creation": {
                "verification": {obligation_id: {"probes": {"preserve_content": 1.0}}}
            }
        }
    }

    assert [item.code for item in missing_probe_diagnostics({}, definition, bindings)] == ["missing-probe"]

    probe = tmp_path / "preserve.probe.yaml"
    write_preserve_content_probe(probe)
    probes, diagnostics = load_probes(probe, definition, bindings)
    assert diagnostics == []
    assert missing_probe_diagnostics(probes, definition, bindings) == []


def test_validate_probes_requires_bindings_for_completeness(tmp_path: Path) -> None:
    probe = tmp_path / "preserve.probe.yaml"
    write_preserve_content_probe(probe)

    assert main([
        "validate-probes",
        str(ROOT / "examples" / "minimal.pml.yaml"),
        str(probe),
        "--require-complete",
    ]) == 1
    assert main([
        "validate-probes",
        str(ROOT / "examples" / "minimal.pml.yaml"),
        str(probe),
        "--bindings",
        str(ROOT / "examples" / "bindings.yaml"),
        "--require-complete",
    ]) == 0


def test_validate_probes_rejects_invalid_bindings_before_coverage_checks(
    tmp_path: Path, capsys
) -> None:
    probe = tmp_path / "preserve.probe.yaml"
    write_preserve_content_probe(probe)
    bindings = tmp_path / "bindings.yaml"
    bindings.write_text("bindings: []\n")

    assert main([
        "validate-probes",
        str(ROOT / "examples" / "minimal.pml.yaml"),
        str(probe),
        "--bindings",
        str(bindings),
        "--require-complete",
    ]) == 1

    output = capsys.readouterr().out
    assert "[schema]" in output
    assert "unbound-probe" not in output
    assert "missing-bindings" not in output


def test_check_probes_does_not_duplicate_binding_load_diagnostics(
    tmp_path: Path, capsys
) -> None:
    product = product_copy(tmp_path)
    (tmp_path / "product-pml" / "bindings.yaml").write_text("[")
    probe = tmp_path / "preserve.probe.yaml"
    write_preserve_content_probe(probe)

    assert main([
        "check",
        str(owner_definition_path(product)),
        str(product),
        "--probes",
        str(probe),
    ]) == 1

    assert capsys.readouterr().out.count("[yaml]") == 1


def test_check_probes_validates_recorded_evidence(tmp_path: Path) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    probe_path = tmp_path / "preserve.probe.yaml"
    write_preserve_content_probe(probe_path)

    assert main(["check", str(owner_definition_path(product)), str(product), "--probes", str(probe_path)]) == 1

    probes, diagnostics = load_probes(probe_path, definition)
    assert diagnostics == []
    state_path = product / ".pml" / "state" / "domains" / "notes" / "features" / "creation.state.yaml"
    state = yaml.safe_load(state_path.read_text())
    state["obligations"]["domains.notes.features.creation.rules.preserve_content"]["evidence"]["deterministic_probe"] = {
        "preserve_content": {
            "result": "passed",
            "input_fingerprint": state["input_fingerprint"],
            "recorded": "2026-07-27T10:00:00Z",
            "observation": "Probe completed.",
            "report_id": "probe_run",
            "report_digest": f"sha256:{'3' * 64}",
            "verifier": {
                "agent": "probe runner",
                "provider": "pml",
                "model": "probe runner",
                "effort": "low",
            },
            "probe": "preserve_content",
            "probe_fingerprint": probe_fingerprint(probes["preserve_content"]),
        }
    }
    state_path.write_text(yaml.safe_dump(state, sort_keys=False))

    assert main(["check", str(owner_definition_path(product)), str(product), "--probes", str(probe_path)]) == 0

    state["obligations"]["domains.notes.features.creation.rules.preserve_content"][
        "evidence"
    ]["deterministic_probe"]["preserve_content"]["probe"] = "different_probe"
    state_path.write_text(yaml.safe_dump(state, sort_keys=False))

    assert main([
        "check",
        str(owner_definition_path(product)),
        str(product),
        "--probes",
        str(probe_path),
    ]) == 1


def test_probe_discovery_accepts_exact_entry_and_file_limits(tmp_path: Path) -> None:
    definition = minimal_definition()
    entry_root = tmp_path / "entry-limit"
    entry_root.mkdir()
    nested = entry_root / "nested"
    nested.mkdir()
    write_probe(nested / "accepted.probe.yaml", "accepted")
    for index in range(MAX_PROBE_DISCOVERY_ENTRIES - 2):
        (entry_root / f"entry_{index}.txt").write_text("ignored\n")

    probes, diagnostics = load_probes(entry_root, definition)

    assert list(probes) == ["accepted"]
    assert diagnostics == []

    file_root = tmp_path / "file-limit"
    file_root.mkdir()
    for index in range(MAX_PROBE_FILES):
        write_probe(file_root / f"probe_{index:02d}.probe.yaml", f"probe_{index}")

    probes, diagnostics = load_probes(file_root, definition)

    assert list(probes) == [f"probe_{index}" for index in range(MAX_PROBE_FILES)]
    assert diagnostics == []


def test_probe_discovery_rejects_entry_and_file_limit_plus_one(tmp_path: Path) -> None:
    definition = minimal_definition()
    entry_root = tmp_path / "entry-limit"
    entry_root.mkdir()
    write_probe(entry_root / "accepted.probe.yaml", "accepted")
    for index in range(MAX_PROBE_DISCOVERY_ENTRIES):
        (entry_root / f"entry_{index}.txt").write_text("ignored\n")

    probes, diagnostics = load_probes(entry_root, definition)

    assert probes == {}
    assert [(item.code, item.path) for item in diagnostics] == [
        ("probe-limit", str(entry_root))
    ]

    file_root = tmp_path / "file-limit"
    file_root.mkdir()
    for index in range(MAX_PROBE_FILES + 1):
        write_probe(file_root / f"probe_{index:02d}.probe.yaml", f"probe_{index}")

    probes, diagnostics = load_probes(file_root, definition)

    assert probes == {}
    assert [(item.code, item.path) for item in diagnostics] == [
        ("probe-limit", str(file_root))
    ]


def test_probe_loader_rejects_oversized_file_before_yaml_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    definition = minimal_definition()
    root = tmp_path / "probes"
    root.mkdir()
    write_probe(root / "a-small.probe.yaml", "small")
    probe = root / "z-oversized.probe.yaml"
    probe.write_bytes(b"x" * (MAX_PROBE_FILE_BYTES + 1))

    def unexpected_parse(*args, **kwargs):
        raise AssertionError("oversized probe must not reach the YAML parser")

    monkeypatch.setattr("pml.probes.yaml.load", unexpected_parse)
    probes, diagnostics = load_probes(root, definition)

    assert probes == {}
    assert [item.code for item in diagnostics] == ["probe-size"]


@pytest.mark.parametrize("kind", ["root", "nested", "file"])
def test_probe_discovery_rejects_symbolic_links(tmp_path: Path, kind: str) -> None:
    definition = minimal_definition()
    root = tmp_path / "probes"
    target = tmp_path / "target"
    target.mkdir()
    write_probe(target / "accepted.probe.yaml", "accepted")

    if kind == "root":
        root.symlink_to(target, target_is_directory=True)
        source = root
    elif kind == "nested":
        root.mkdir()
        (root / "nested").symlink_to(target, target_is_directory=True)
        source = root
    else:
        root.mkdir()
        (root / "linked.probe.yaml").symlink_to(target / "accepted.probe.yaml")
        source = root

    probes, diagnostics = load_probes(source, definition)

    assert probes == {}
    assert [item.code for item in diagnostics] == ["probe-path"]
    assert "symbolic links" in diagnostics[0].message


def test_probe_discovery_rejects_non_regular_probe_entries(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("the platform does not support FIFO conformance coverage")
    definition = minimal_definition()
    root = tmp_path / "probes"
    root.mkdir()
    fifo = root / "not-a-file.probe.yaml"
    os.mkfifo(fifo)

    probes, diagnostics = load_probes(root, definition)

    assert probes == {}
    assert [(item.code, item.path) for item in diagnostics] == [
        ("probe-path", str(fifo))
    ]
    assert "regular files" in diagnostics[0].message


def test_probe_discovery_preserves_first_duplicate_id_in_path_order(
    tmp_path: Path,
) -> None:
    definition = minimal_definition()
    root = tmp_path / "probes"
    root.mkdir()
    write_probe(root / "z-last.probe.yaml", "duplicate")
    write_probe(root / "a-first.probe.yaml", "duplicate")

    probes, diagnostics = load_probes(root, definition)

    assert list(probes) == ["duplicate"]
    assert [(item.code, item.path) for item in diagnostics] == [
        ("duplicate-probe", f"{root / 'z-last.probe.yaml'}:probe")
    ]


def test_probe_diagnostics_are_path_ordered(tmp_path: Path) -> None:
    definition = minimal_definition()
    root = tmp_path / "probes"
    root.mkdir()
    missing = "domains.notes.features.creation.rules.unknown"
    write_probe(root / "z-last.probe.yaml", "z_last", verifies=missing)
    write_probe(root / "a-first.probe.yaml", "a_first", verifies=missing)

    probes, diagnostics = load_probes(root, definition)

    assert list(probes) == ["a_first", "z_last"]
    assert [item.path for item in diagnostics] == [
        f"{root / 'a-first.probe.yaml'}:verifies",
        f"{root / 'z-last.probe.yaml'}:verifies",
    ]


def test_probe_schema_enforces_exact_step_limit(tmp_path: Path) -> None:
    definition = minimal_definition()
    accepted = tmp_path / "accepted.probe.yaml"
    write_probe(accepted, "accepted", steps=64)

    probes, diagnostics = load_probes(accepted, definition)

    assert list(probes) == ["accepted"]
    assert diagnostics == []

    rejected = tmp_path / "rejected.probe.yaml"
    write_probe(rejected, "rejected", steps=65)
    probes, diagnostics = load_probes(rejected, definition)

    assert probes == {}
    assert [item.code for item in diagnostics] == ["schema"]
    assert "is too long" in diagnostics[0].message


def test_probe_limits_reject_every_probe_loading_cli_before_partial_use(
    tmp_path: Path, capsys
) -> None:
    product = product_copy(tmp_path)
    root = tmp_path / "probes"
    root.mkdir()
    for index in range(MAX_PROBE_FILES + 1):
        write_probe(root / f"probe_{index}.probe.yaml", f"probe_{index}")
    invalid_report = tmp_path / "invalid-report.yaml"
    invalid_report.write_text("[")
    state_path = product / ".pml/state/domains/notes/features/creation.state.yaml"
    original_state = state_path.read_bytes()

    assert main([
        "validate-probes",
        str(owner_definition_path(product)),
        str(root),
    ]) == 1
    assert "[probe-limit]" in capsys.readouterr().out

    assert main([
        "check",
        str(owner_definition_path(product)),
        str(product),
        "--probes",
        str(root),
    ]) == 1
    assert "[probe-limit]" in capsys.readouterr().out

    assert main([
        "ingest-report",
        str(owner_definition_path(product)),
        str(product),
        str(root),
        str(invalid_report),
    ]) == 1
    assert "[probe-limit]" in capsys.readouterr().out
    assert state_path.read_bytes() == original_state
