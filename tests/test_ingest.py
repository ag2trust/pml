from pathlib import Path
import shutil

import yaml

from pml.cli import main
from pml.ingest import ingest_report
from pml.probes import load_probes, probe_fingerprint
from pml.project_state import (
    bindings_digest,
    validate_probe_evidence,
    validate_product_state,
)
from pml.validator import load_document


ROOT = Path(__file__).resolve().parents[1]
OBLIGATION = "domains.notes.features.creation.rules.preserve_content"


def write_probe(path: Path) -> None:
    path.write_text(
        f"""\
pml_probe: "0.1"
probe: preserve_content
verifies: {OBLIGATION}
env: staging
steps:
  - cli: [notes, verify-content]
    as: member
    expect: {{exit: 0}}
"""
    )


def write_report(path: Path) -> None:
    path.write_text(
        f"""\
verification: run_1
version: working_tree
recorded: "2026-07-22T10:00:00Z"
environment: local_integrated
verifier:
  agent: runner
  provider: pml
  model: probe_runner
  effort: low
targets:
  - domains.notes.features.creation
verdict: verified
checks:
  - target: {OBLIGATION}
    result: passed
    method: deterministic_probe
    probe: preserve_content
    observation: Probe exited successfully.
limitations: []
"""
    )


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


def owner_bindings_path(product: Path) -> Path:
    return product.parent / "product-pml" / "bindings.yaml"


def approve_bindings(product: Path, bindings: dict) -> None:
    owner_bindings_path(product).write_text(yaml.safe_dump(bindings, sort_keys=False))
    lock_path = product / ".pml" / "pml.lock"
    lock = yaml.safe_load(lock_path.read_text())
    lock["bindings"]["digest"] = bindings_digest(bindings)
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False))


def test_ingests_current_probe_evidence(tmp_path: Path) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    probe_path = tmp_path / "preserve.probe.yaml"
    report_path = tmp_path / "report.yaml"
    write_probe(probe_path)
    write_report(report_path)
    probes, diagnostics = load_probes(probe_path, definition)
    assert diagnostics == []

    assert ingest_report(report_path, product, definition, probes) == []
    assert validate_product_state(product, definition) == []
    assert validate_probe_evidence(product, definition, probes) == []

    state_path = (
        product
        / ".pml/state/domains/notes/features/creation.state.yaml"
    )
    state = yaml.safe_load(state_path.read_text())
    evidence = state["obligations"][OBLIGATION]["evidence"]
    record = evidence["deterministic_probe"]["preserve_content"]
    assert record["probe_fingerprint"] == probe_fingerprint(
        probes["preserve_content"]
    )


def test_cli_ingests_valid_report(tmp_path: Path) -> None:
    product = product_copy(tmp_path)
    probe_path = tmp_path / "preserve.probe.yaml"
    report_path = tmp_path / "report.yaml"
    write_probe(probe_path)
    write_report(report_path)

    assert main([
        "ingest-report",
        str(ROOT / "examples" / "minimal.pml.yaml"),
        str(product),
        str(probe_path),
        str(report_path),
    ]) == 0


def test_ingestion_rejects_mismatched_bindings_digest_without_writing(
    tmp_path: Path,
) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    probe_path = tmp_path / "preserve.probe.yaml"
    report_path = tmp_path / "report.yaml"
    write_probe(probe_path)
    write_report(report_path)
    probes, _ = load_probes(probe_path, definition)
    state_path = (
        product
        / ".pml/state/domains/notes/features/creation.state.yaml"
    )
    original = state_path.read_text()
    lock_path = product / ".pml" / "pml.lock"
    lock = yaml.safe_load(lock_path.read_text())
    lock["bindings"]["digest"] = f"sha256:{'0' * 64}"
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False))

    diagnostics = ingest_report(
        report_path, product, definition, probes
    )

    assert {item.code for item in diagnostics} == {"bindings-digest"}
    assert state_path.read_text() == original


def test_rejects_probe_without_coverage_binding(tmp_path: Path) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    bindings_path = owner_bindings_path(product)
    bindings = yaml.safe_load(bindings_path.read_text())
    plans = bindings["bindings"]["domains.notes.features.creation"]["verification"]
    plans[OBLIGATION] = {"agent_judgment": 1.0}
    approve_bindings(product, bindings)
    probe_path = tmp_path / "preserve.probe.yaml"
    report_path = tmp_path / "report.yaml"
    write_probe(probe_path)
    write_report(report_path)
    probes, _ = load_probes(probe_path, definition)

    diagnostics = ingest_report(report_path, product, definition, probes)

    assert any(item.code == "unbound-probe" for item in diagnostics)


def test_reports_missing_verification_plan_without_follow_on_errors(
    tmp_path: Path,
) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    bindings_path = owner_bindings_path(product)
    bindings = yaml.safe_load(bindings_path.read_text())
    plans = bindings["bindings"]["domains.notes.features.creation"]["verification"]
    del plans[OBLIGATION]
    bindings_path.write_text(yaml.safe_dump(bindings, sort_keys=False))
    probe_path = tmp_path / "preserve.probe.yaml"
    report_path = tmp_path / "report.yaml"
    write_probe(probe_path)
    write_report(report_path)
    probes, _ = load_probes(probe_path, definition)

    diagnostics = ingest_report(report_path, product, definition, probes)

    assert [item.code for item in diagnostics] == ["missing-verification-plan"]


def test_invalid_existing_state_is_not_overwritten(tmp_path: Path) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    state_path = (
        product
        / ".pml/state/domains/notes/features/creation.state.yaml"
    )
    state_path.write_text("[")
    original = state_path.read_text()
    probe_path = tmp_path / "preserve.probe.yaml"
    report_path = tmp_path / "report.yaml"
    write_probe(probe_path)
    write_report(report_path)
    probes, _ = load_probes(probe_path, definition)

    diagnostics = ingest_report(report_path, product, definition, probes)

    assert any(item.code == "yaml" for item in diagnostics)
    assert state_path.read_text() == original


def test_report_requires_method_specific_identity(tmp_path: Path) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    report_path = tmp_path / "report.yaml"
    write_report(report_path)
    report = yaml.safe_load(report_path.read_text())
    del report["checks"][0]["probe"]
    report_path.write_text(yaml.safe_dump(report, sort_keys=False))

    diagnostics = ingest_report(report_path, product, definition, {})

    assert any(item.code == "schema" for item in diagnostics)


def test_agent_report_requires_nonempty_reproduction(tmp_path: Path) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    report_path = tmp_path / "report.yaml"
    write_report(report_path)
    report = yaml.safe_load(report_path.read_text())
    report["checks"][0]["method"] = "agent_judgment"
    del report["checks"][0]["probe"]
    report["checks"][0]["reproduction"] = []
    report_path.write_text(yaml.safe_dump(report, sort_keys=False))

    diagnostics = ingest_report(report_path, product, definition, {})

    assert any(item.code == "schema" for item in diagnostics)


def test_report_rejects_empty_probe_and_artifact_identifiers(tmp_path: Path) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    report_path = tmp_path / "report.yaml"
    write_report(report_path)
    report = yaml.safe_load(report_path.read_text())
    report["checks"][0]["probe"] = ""
    report["checks"][0]["evidence"] = []
    report_path.write_text(yaml.safe_dump(report, sort_keys=False))

    diagnostics = ingest_report(report_path, product, definition, {})

    assert {item.code for item in diagnostics} == {"schema"}


def test_probe_artifacts_are_preserved(tmp_path: Path) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    probe_path = tmp_path / "preserve.probe.yaml"
    report_path = tmp_path / "report.yaml"
    write_probe(probe_path)
    write_report(report_path)
    report = yaml.safe_load(report_path.read_text())
    report["checks"][0]["evidence"] = ["evidence/preserve-content.json"]
    report_path.write_text(yaml.safe_dump(report, sort_keys=False))
    probes, _ = load_probes(probe_path, definition)

    assert ingest_report(report_path, product, definition, probes) == []

    state_path = (
        product
        / ".pml/state/domains/notes/features/creation.state.yaml"
    )
    state = yaml.safe_load(state_path.read_text())
    record = state["obligations"][OBLIGATION]["evidence"][
        "deterministic_probe"
    ]["preserve_content"]
    assert record["artifacts"] == ["evidence/preserve-content.json"]
