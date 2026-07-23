from pathlib import Path
import shutil

import yaml

from pml.ingest import ingest_report
from pml.probes import load_probes, missing_probe_diagnostics, probe_fingerprint
from pml.project_state import validate_probe_evidence, validate_product_state
from pml.validator import load_document


ROOT = Path(__file__).resolve().parents[1]


def test_approved_probe_is_valid_and_bound_to_obligation() -> None:
    definition, diagnostics = load_document(ROOT / "examples" / "assistant-creation.pml.yaml")
    assert diagnostics == []
    assert definition is not None
    probes, probe_diagnostics = load_probes(ROOT / "examples" / "assistant-persistence.probe.yaml", definition)
    assert probe_diagnostics == []
    assert probes["assistant_config_persistence"]["verifies"].endswith("use_cases.create_from_scratch")
    assert probe_fingerprint(probes["assistant_config_persistence"]).startswith("sha256:")


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
    codes = {item.code for item in diagnostics}
    assert "undefined-variable" in codes
    assert "undefined-reference" in codes


def test_reports_deterministic_obligations_without_probes() -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    diagnostics = missing_probe_diagnostics({}, definition)
    assert {item.code for item in diagnostics} == {"missing-probe"}
    assert len(diagnostics) == 3


def test_ingests_current_probe_evidence(tmp_path: Path) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = tmp_path / "product"
    shutil.copytree(ROOT / "examples" / "product-repository", product)
    probe_path = tmp_path / "preserve.probe.yaml"
    probe_path.write_text(
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
    probes, diagnostics = load_probes(probe_path, definition)
    assert diagnostics == []
    report_path = tmp_path / "report.yaml"
    report = {
        "verification": "run-1",
        "version": "working-tree",
        "recorded": "2026-07-22T10:00:00Z",
        "environment": "local_integrated",
        "verifier": {"agent": "runner", "provider": "pml", "model": "probe-runner", "effort": "low"},
        "targets": ["domains.notes.features.creation.rules.preserve_content"],
        "verdict": "verified",
        "checks": [{
            "target": "domains.notes.features.creation.rules.preserve_content",
            "result": "passed",
            "method": "deterministic_probe",
            "probe": "preserve_content",
            "observation": "Probe exited successfully.",
        }],
        "limitations": [],
    }
    report_path.write_text(yaml.safe_dump(report, sort_keys=False))
    assert ingest_report(report_path, product, definition, probes) == []
    assert validate_product_state(product, definition) == []
    assert validate_probe_evidence(product, definition, probes) == []
