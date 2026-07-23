from pathlib import Path

from pml.probes import load_probes, missing_probe_diagnostics, probe_fingerprint
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
