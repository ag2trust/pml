from pathlib import Path
import shutil

import yaml

from pml.cli import main
from pml.probes import load_probes, missing_probe_diagnostics, probe_fingerprint
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


def test_approved_probe_is_valid_and_bound_to_obligation() -> None:
    definition, diagnostics = load_document(ROOT / "examples" / "assistant-creation.pml.yaml")
    assert diagnostics == []
    assert definition is not None

    probes, probe_diagnostics = load_probes(ROOT / "examples" / "assistant-persistence.probe.yaml", definition)

    assert probe_diagnostics == []
    assert probes["assistant_config_persistence"]["verifies"].endswith("use_cases.create_from_scratch")
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
