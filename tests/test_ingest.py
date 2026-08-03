from pathlib import Path
import shutil

import yaml

from pml.cli import main
from pml.ingest import MAX_REPORT_FILE_BYTES, ingest_report
from pml.probes import load_probes, probe_fingerprint
from pml.project_state import (
    MAX_STATE_FILE_BYTES,
    bindings_digest,
    canonical_hash,
    input_fingerprint,
    validate_probe_evidence,
    validate_product_state,
)
from pml.status import product_status
from pml.validator import load_document


ROOT = Path(__file__).resolve().parents[1]
OBLIGATION = "domains.notes.features.creation.rules.preserve_content"
USE_CASE = "domains.notes.features.creation.use_cases.create_note"


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


def write_implementation_only_report(path: Path) -> None:
    path.write_text(
        f"""\
verification: run_implementation_1
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
verdict: incomplete
implementation:
  - target: {OBLIGATION}
    status: partial
    observation: The obligation is only partially implemented.
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


def owner_definition_path(product: Path) -> Path:
    return product.parent / "product-pml" / "minimal.pml.yaml"


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

    assert ingest_report(
        report_path,
        product,
        definition,
        probes,
        definition_source=owner_definition_path(product),
    ) == []
    assert validate_product_state(
        product,
        definition,
        definition_source=owner_definition_path(product),
    ) == []
    assert validate_probe_evidence(
        product,
        definition,
        probes,
        definition_source=owner_definition_path(product),
    ) == []

    state_path = (
        product
        / ".pml/state/domains/notes/features/creation.state.yaml"
    )
    state = yaml.safe_load(state_path.read_text())
    evidence = state["obligations"][OBLIGATION]["evidence"]
    record = evidence["deterministic_probe"]["preserve_content"]
    report = yaml.safe_load(report_path.read_text())
    assert record["report_id"] == "run_1"
    assert record["report_digest"] == canonical_hash(report)
    assert record["recorded"] == report["recorded"]
    assert record["verifier"] == report["verifier"]
    assert record["probe"] == "preserve_content"
    assert record["probe_fingerprint"] == probe_fingerprint(
        probes["preserve_content"]
    )


def test_report_rejects_duplicate_evidence_lanes_without_writing(
    tmp_path: Path,
) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    probe_path = tmp_path / "preserve.probe.yaml"
    report_path = tmp_path / "report.yaml"
    write_probe(probe_path)
    write_report(report_path)
    report = yaml.safe_load(report_path.read_text())
    report["checks"].append(dict(report["checks"][0]))
    report["checks"].extend([
        {
            "target": USE_CASE,
            "result": "passed",
            "method": "agent_judgment",
            "observation": "The use case completed.",
            "reproduction": ["Create a note."],
        },
        {
            "target": USE_CASE,
            "result": "failed",
            "method": "agent_judgment",
            "observation": "The repeated check failed.",
            "reproduction": ["Create another note."],
        },
    ])
    report_path.write_text(yaml.safe_dump(report, sort_keys=False))
    probes, diagnostics = load_probes(probe_path, definition)
    assert diagnostics == []
    state_path = (
        product / ".pml/state/domains/notes/features/creation.state.yaml"
    )
    original = state_path.read_bytes()

    diagnostics = ingest_report(
        report_path,
        product,
        definition,
        probes,
        definition_source=owner_definition_path(product),
    )

    assert {item.code for item in diagnostics} == {"duplicate-check"}
    assert len(diagnostics) == 2
    assert state_path.read_bytes() == original


def test_report_preserves_distinct_deterministic_probe_results(
    tmp_path: Path,
) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    bindings = yaml.safe_load(owner_bindings_path(product).read_text())
    plan = bindings["bindings"]["domains.notes.features.creation"][
        "verification"
    ][OBLIGATION]
    plan["probes"] = {"preserve_content": 0.5, "restart_content": 0.5}
    approve_bindings(product, bindings)
    probes = {
        "preserve_content": {"probe": "preserve_content", "verifies": OBLIGATION},
        "restart_content": {"probe": "restart_content", "verifies": OBLIGATION},
    }
    report_path = tmp_path / "report.yaml"
    write_report(report_path)
    report = yaml.safe_load(report_path.read_text())
    second = dict(report["checks"][0])
    second["probe"] = "restart_content"
    second["observation"] = "Restart probe exited successfully."
    report["checks"].append(second)
    report_path.write_text(yaml.safe_dump(report, sort_keys=False))

    assert ingest_report(
        report_path,
        product,
        definition,
        probes,
        definition_source=owner_definition_path(product),
    ) == []
    state = yaml.safe_load((
        product / ".pml/state/domains/notes/features/creation.state.yaml"
    ).read_text())
    evidence = state["obligations"][OBLIGATION]["evidence"][
        "deterministic_probe"
    ]
    assert set(evidence) == {"preserve_content", "restart_content"}


def test_agent_and_human_evidence_store_report_origin(tmp_path: Path) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    bindings = yaml.safe_load(owner_bindings_path(product).read_text())
    bindings["bindings"]["domains.notes.features.creation"]["verification"][
        USE_CASE
    ] = {"agent_judgment": 0.5, "human_attestation": 0.5}
    approve_bindings(product, bindings)
    report_path = tmp_path / "report.yaml"
    write_report(report_path)
    report = yaml.safe_load(report_path.read_text())
    report["checks"] = [
        {
            "target": USE_CASE,
            "result": "passed",
            "method": "agent_judgment",
            "observation": "The use case completed.",
            "reproduction": ["Create a note."],
        },
        {
            "target": USE_CASE,
            "result": "passed",
            "method": "human_attestation",
            "observation": "The owner observed the use case.",
            "attester": "Product owner",
        },
    ]
    report_path.write_text(yaml.safe_dump(report, sort_keys=False))

    assert ingest_report(
        report_path,
        product,
        definition,
        {},
        definition_source=owner_definition_path(product),
    ) == []
    state = yaml.safe_load((
        product / ".pml/state/domains/notes/features/creation.state.yaml"
    ).read_text())
    evidence = state["obligations"][USE_CASE]["evidence"]
    digest = canonical_hash(report)
    for record in evidence.values():
        assert record["report_id"] == report["verification"]
        assert record["report_digest"] == digest
        assert record["recorded"] == report["recorded"]
        assert record["verifier"] == report["verifier"]
    assert evidence["agent_judgment"]["reproduction"] == ["Create a note."]
    assert evidence["human_attestation"]["attester"] == "Product owner"


def test_cli_ingests_valid_report(tmp_path: Path) -> None:
    product = product_copy(tmp_path)
    probe_path = tmp_path / "preserve.probe.yaml"
    report_path = tmp_path / "report.yaml"
    write_probe(probe_path)
    write_report(report_path)

    assert main([
        "ingest-report",
        str(owner_definition_path(product)),
        str(product),
        str(probe_path),
        str(report_path),
    ]) == 0


def test_implementation_only_report_updates_implementation_state(
    tmp_path: Path,
) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    report_path = tmp_path / "implementation-report.yaml"
    write_implementation_only_report(report_path)
    state_path = (
        product
        / ".pml/state/domains/notes/features/creation.state.yaml"
    )

    assert ingest_report(
        report_path,
        product,
        definition,
        {},
        definition_source=owner_definition_path(product),
    ) == []
    state = yaml.safe_load(state_path.read_text())
    assert state["obligations"][OBLIGATION]["implemented"] == "partial"
    assert state["obligations"][OBLIGATION]["evidence"] == {
        "deterministic_probe": {}
    }
    implementation = state["obligations"][OBLIGATION]["implementation"]
    assert implementation == {
        "status": "partial",
        "observation": "The obligation is only partially implemented.",
        "report_id": "run_implementation_1",
        "report_digest": canonical_hash(yaml.safe_load(report_path.read_text())),
        "recorded": "2026-07-22T10:00:00Z",
        "verifier": {
            "agent": "runner",
            "provider": "pml",
            "model": "probe_runner",
            "effort": "low",
        },
    }
    assert validate_product_state(
        product, definition, definition_source=owner_definition_path(product)
    ) == []


def test_mixed_report_updates_implementation_and_evidence(tmp_path: Path) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    probe_path = tmp_path / "preserve.probe.yaml"
    report_path = tmp_path / "mixed-report.yaml"
    write_probe(probe_path)
    write_report(report_path)
    report = yaml.safe_load(report_path.read_text())
    report["implementation"] = [{
        "target": OBLIGATION,
        "status": "partial",
        "observation": "The obligation is only partially implemented.",
    }]
    report_path.write_text(yaml.safe_dump(report, sort_keys=False))
    probes, diagnostics = load_probes(probe_path, definition)
    assert diagnostics == []

    assert ingest_report(
        report_path,
        product,
        definition,
        probes,
        definition_source=owner_definition_path(product),
    ) == []

    state_path = (
        product
        / ".pml/state/domains/notes/features/creation.state.yaml"
    )
    state = yaml.safe_load(state_path.read_text())
    obligation_state = state["obligations"][OBLIGATION]
    assert obligation_state["implemented"] == "partial"
    assert "preserve_content" in obligation_state["evidence"]["deterministic_probe"]


def test_implementation_report_rejects_unknown_obligation(tmp_path: Path) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    report_path = tmp_path / "implementation-report.yaml"
    write_implementation_only_report(report_path)
    report = yaml.safe_load(report_path.read_text())
    report["implementation"][0]["target"] = "domains.notes.features.creation.rules.unknown"
    report_path.write_text(yaml.safe_dump(report, sort_keys=False))
    state_path = (
        product
        / ".pml/state/domains/notes/features/creation.state.yaml"
    )
    original = state_path.read_text()

    diagnostics = ingest_report(
        report_path,
        product,
        definition,
        {},
        definition_source=owner_definition_path(product),
    )

    assert {item.code for item in diagnostics} == {"undefined-reference"}
    assert state_path.read_text() == original


def test_report_rejects_undeclared_targets_before_writing(tmp_path: Path) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    report_path = tmp_path / "implementation-report.yaml"
    write_implementation_only_report(report_path)
    report = yaml.safe_load(report_path.read_text())
    report["targets"] = ["domains.notes.features.unknown"]
    report_path.write_text(yaml.safe_dump(report, sort_keys=False))
    state_path = (
        product
        / ".pml/state/domains/notes/features/creation.state.yaml"
    )
    original = state_path.read_text()

    diagnostics = ingest_report(
        report_path,
        product,
        definition,
        {},
        definition_source=owner_definition_path(product),
    )

    assert {item.code for item in diagnostics} == {
        "undefined-reference", "undeclared-target"
    }
    assert state_path.read_text() == original


def test_report_rejects_duplicate_implementation_assessments(tmp_path: Path) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    report_path = tmp_path / "implementation-report.yaml"
    write_implementation_only_report(report_path)
    report = yaml.safe_load(report_path.read_text())
    report["implementation"].append(dict(report["implementation"][0]))
    report_path.write_text(yaml.safe_dump(report, sort_keys=False))
    state_path = (
        product
        / ".pml/state/domains/notes/features/creation.state.yaml"
    )
    original = state_path.read_text()

    diagnostics = ingest_report(
        report_path,
        product,
        definition,
        {},
        definition_source=owner_definition_path(product),
    )

    assert {item.code for item in diagnostics} == {"duplicate-implementation"}
    assert state_path.read_text() == original


def test_ingestion_rejects_oversized_report_before_parsing(tmp_path: Path) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    report_path = tmp_path / "oversized-report.yaml"
    report_path.write_bytes(
        b"limitations:\n  - " + b"x" * MAX_REPORT_FILE_BYTES
    )
    state_path = (
        product
        / ".pml/state/domains/notes/features/creation.state.yaml"
    )
    original = state_path.read_bytes()

    diagnostics = ingest_report(
        report_path,
        product,
        definition,
        {},
        definition_source=owner_definition_path(product),
    )

    assert {item.code for item in diagnostics} == {"report-size"}
    assert state_path.read_bytes() == original


def test_ingestion_rejects_oversized_generated_state_without_writing(
    tmp_path: Path,
) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    bindings = yaml.safe_load(owner_bindings_path(product).read_text())
    plan = bindings["bindings"]["domains.notes.features.creation"][
        "verification"
    ][OBLIGATION]
    probe_ids = [f"large_evidence_{index}" for index in range(4)]
    plan["probes"] = {probe_id: 0.25 for probe_id in probe_ids}
    approve_bindings(product, bindings)
    report_path = tmp_path / "oversized-report.yaml"
    write_report(report_path)
    report = yaml.safe_load(report_path.read_text())
    artifacts = [f"{index:04d}" + "x" * 4076 for index in range(64)]
    report["checks"] = [{
        "target": OBLIGATION,
        "result": "passed",
        "method": "deterministic_probe",
        "probe": probe_id,
        "observation": "Probe exited successfully.",
        "evidence": list(artifacts),
    } for probe_id in probe_ids]
    report_path.write_text(yaml.safe_dump(report, sort_keys=False))
    probes = {probe_id: {"verifies": OBLIGATION} for probe_id in probe_ids}
    state_path = (
        product
        / ".pml/state/domains/notes/features/creation.state.yaml"
    )
    original = state_path.read_bytes()

    diagnostics = ingest_report(
        report_path,
        product,
        definition,
        probes,
        definition_source=owner_definition_path(product),
    )

    assert {item.code for item in diagnostics} == {"state-size"}
    assert state_path.read_bytes() == original


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
        report_path,
        product,
        definition,
        probes,
        definition_source=owner_definition_path(product),
    )

    assert {item.code for item in diagnostics} == {"bindings-digest"}
    assert state_path.read_text() == original


def test_partial_ingestion_clears_evidence_from_prior_bindings(
    tmp_path: Path,
) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    bindings_path = owner_bindings_path(product)
    bindings = yaml.safe_load(bindings_path.read_text())
    plan = bindings["bindings"]["domains.notes.features.creation"][
        "verification"
    ][OBLIGATION]
    plan["probes"]["preserve_content"] = 0.5
    plan["agent_judgment"] = 0.5
    approve_bindings(product, bindings)

    state_path = (
        product
        / ".pml/state/domains/notes/features/creation.state.yaml"
    )
    state = yaml.safe_load(state_path.read_text())
    state["bindings_digest"] = bindings_digest(bindings)
    state["obligations"][OBLIGATION]["evidence"]["agent_judgment"] = {
        "result": "passed",
        "input_fingerprint": state["input_fingerprint"],
        "recorded": "2026-07-31T10:00:00Z",
        "observation": "Passed under the prior coverage policy.",
        "report_id": "prior_policy",
        "report_digest": f"sha256:{'3' * 64}",
        "verifier": {
            "agent": "prior verifier",
            "provider": "pml",
            "model": "prior model",
            "effort": "low",
        },
        "reproduction": ["Evaluate the obligation."],
    }
    state_path.write_text(yaml.safe_dump(state, sort_keys=False))

    plan["probes"]["preserve_content"] = 0.75
    plan["agent_judgment"] = 0.25
    approve_bindings(product, bindings)
    probe_path = tmp_path / "preserve.probe.yaml"
    report_path = tmp_path / "report.yaml"
    write_probe(probe_path)
    write_report(report_path)
    probes, probe_diagnostics = load_probes(
        probe_path, definition, bindings
    )
    assert probe_diagnostics == []

    assert ingest_report(
        report_path,
        product,
        definition,
        probes,
        definition_source=owner_definition_path(product),
    ) == []

    reconciled = yaml.safe_load(state_path.read_text())
    evidence = reconciled["obligations"][OBLIGATION]["evidence"]
    assert set(evidence) == {"deterministic_probe"}
    assert reconciled["bindings_digest"] == bindings_digest(bindings)
    statuses = product_status(
        product,
        definition,
        definition_source=owner_definition_path(product),
    )
    preserve_status = next(
        item
        for node in statuses
        for item in node.obligations
        if item.obligation_id == OBLIGATION
    )
    assert (preserve_status.signal, preserve_status.verified_coverage) == (
        "PARTIAL",
        0.75,
    )


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

    diagnostics = ingest_report(
        report_path,
        product,
        definition,
        probes,
        definition_source=owner_definition_path(product),
    )

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

    diagnostics = ingest_report(
        report_path,
        product,
        definition,
        probes,
        definition_source=owner_definition_path(product),
    )

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

    diagnostics = ingest_report(
        report_path,
        product,
        definition,
        probes,
        definition_source=owner_definition_path(product),
    )

    assert any(item.code == "yaml" for item in diagnostics)
    assert state_path.read_text() == original


def test_oversized_product_state_is_not_read_or_overwritten(
    tmp_path: Path,
) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    state_path = (
        product
        / ".pml/state/domains/notes/features/creation.state.yaml"
    )
    oversized = b"x" * (MAX_STATE_FILE_BYTES + 1)
    state_path.write_bytes(oversized)
    probe_path = tmp_path / "preserve.probe.yaml"
    report_path = tmp_path / "report.yaml"
    write_probe(probe_path)
    write_report(report_path)
    probes, _ = load_probes(probe_path, definition)

    diagnostics = ingest_report(
        report_path,
        product,
        definition,
        probes,
        definition_source=owner_definition_path(product),
    )

    assert [item.code for item in diagnostics] == ["state-size"]
    assert state_path.read_bytes() == oversized


def test_report_requires_method_specific_identity(tmp_path: Path) -> None:
    definition, _ = load_document(ROOT / "examples" / "minimal.pml.yaml")
    assert definition is not None
    product = product_copy(tmp_path)
    report_path = tmp_path / "report.yaml"
    write_report(report_path)
    report = yaml.safe_load(report_path.read_text())
    del report["checks"][0]["probe"]
    report_path.write_text(yaml.safe_dump(report, sort_keys=False))

    diagnostics = ingest_report(
        report_path,
        product,
        definition,
        {},
        definition_source=owner_definition_path(product),
    )

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

    diagnostics = ingest_report(
        report_path,
        product,
        definition,
        {},
        definition_source=owner_definition_path(product),
    )

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

    diagnostics = ingest_report(
        report_path,
        product,
        definition,
        {},
        definition_source=owner_definition_path(product),
    )

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

    assert ingest_report(
        report_path,
        product,
        definition,
        probes,
        definition_source=owner_definition_path(product),
    ) == []

    state_path = (
        product
        / ".pml/state/domains/notes/features/creation.state.yaml"
    )
    state = yaml.safe_load(state_path.read_text())
    record = state["obligations"][OBLIGATION]["evidence"][
        "deterministic_probe"
    ]["preserve_content"]
    assert record["artifacts"] == ["evidence/preserve-content.json"]


def test_ingests_architecture_evidence_with_architecture_bound_paths(tmp_path: Path) -> None:
    definition, diagnostics = load_document(ROOT / "examples" / "architecture-decisions.pml.yaml")
    assert diagnostics == []
    assert definition is not None
    owner = tmp_path / "product-pml"
    owner.mkdir()
    manifest = owner / "architecture-decisions.pml.yaml"
    manifest.write_text(yaml.safe_dump(definition, sort_keys=False))
    product = tmp_path / "product"
    metadata = product / ".pml"
    metadata.mkdir(parents=True)
    runtime = product / "runtime"
    runtime.mkdir()
    (runtime / "selection").write_text("approved\n")
    obligation = "architecture.durable_store.constraints.preserve_committed_records"
    product_obligation = (
        "domains.records.features.preservation.rules.record_remains_available"
    )
    bindings = {
        "pml_bindings": "0.1",
        "bindings": {
            "domains.records.features.preservation": {
                "paths": ["runtime"],
                "verification": {
                    product_obligation: {"agent_judgment": 1.0}
                },
            }
        },
        "architecture": {
            "durable_store": {
                "paths": ["runtime"],
                "verification": {obligation: {"agent_judgment": 1.0}},
            }
        },
    }
    (owner / "bindings.yaml").write_text(yaml.safe_dump(bindings, sort_keys=False))
    (metadata / "pml.lock").write_text(yaml.safe_dump({
        "pml_lock": "0.1",
        "definition": {
            "source": str(manifest),
            "revision": "approved",
            "digest": canonical_hash(definition),
        },
        "bindings": {"digest": bindings_digest(bindings)},
    }, sort_keys=False))
    report = tmp_path / "architecture-report.yaml"
    report.write_text("\n".join([
        "verification: architecture_run",
        "version: working_tree",
        'recorded: "2026-07-29T10:00:00Z"',
        "environment: local_integrated",
        "verifier:",
        "  agent: verifier",
        "  provider: pml",
        "  model: verifier",
        "  effort: low",
        "targets: [architecture.durable_store]",
        "verdict: verified",
        "checks:",
        f"  - target: {obligation}",
        "    result: passed",
        "    method: agent_judgment",
        "    observation: The approved store preserves committed records.",
        "    reproduction: [Run the approved preservation check.]",
        "limitations: []",
        "",
    ]))
    assert ingest_report(
        report,
        product,
        definition,
        {},
        definition_source=manifest,
    ) == []
    state = yaml.safe_load((metadata / "architecture" / "durable_store.state.yaml").read_text())
    assert state["bindings_digest"] == bindings_digest(bindings)
    assert state["input_fingerprint"] == input_fingerprint(product, ["runtime"])
    assert state["obligations"][obligation]["evidence"]["agent_judgment"]["input_fingerprint"] == state["input_fingerprint"]

    state_path = metadata / "architecture" / "durable_store.state.yaml"
    oversized = b"x" * (MAX_STATE_FILE_BYTES + 1)
    state_path.write_bytes(oversized)
    oversized_diagnostics = ingest_report(
        report,
        product,
        definition,
        {},
        definition_source=manifest,
    )
    assert [item.code for item in oversized_diagnostics] == ["state-size"]
    assert state_path.read_bytes() == oversized


def test_ingestion_reconciles_added_architecture_constraint(tmp_path: Path) -> None:
    definition, diagnostics = load_document(
        ROOT / "examples" / "architecture-decisions.pml.yaml"
    )
    assert diagnostics == []
    assert definition is not None
    owner = tmp_path / "product-pml"
    owner.mkdir()
    manifest = owner / "architecture-decisions.pml.yaml"
    product = tmp_path / "product"
    metadata = product / ".pml"
    metadata.mkdir(parents=True)
    runtime = product / "runtime"
    runtime.mkdir()
    original_obligation = (
        "architecture.durable_store.constraints.preserve_committed_records"
    )
    added_obligation = "architecture.durable_store.constraints.recoverable_records"
    bindings = {
        "pml_bindings": "0.1",
        "bindings": {
            "domains.records.features.preservation": {
                "paths": ["runtime"],
                "verification": {
                    "domains.records.features.preservation.rules.record_remains_available": {
                        "agent_judgment": 1.0
                    }
                },
            }
        },
        "architecture": {
            "durable_store": {
                "paths": ["runtime"],
                "verification": {original_obligation: {"agent_judgment": 1.0}},
            }
        },
    }
    manifest.write_text(yaml.safe_dump(definition, sort_keys=False))
    (owner / "bindings.yaml").write_text(yaml.safe_dump(bindings, sort_keys=False))
    lock_path = metadata / "pml.lock"
    lock = {
        "pml_lock": "0.1",
        "definition": {
            "source": str(manifest),
            "revision": "approved",
            "digest": canonical_hash(definition),
        },
        "bindings": {"digest": bindings_digest(bindings)},
    }
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False))
    report = tmp_path / "architecture-report.yaml"
    report.write_text("\n".join([
        "verification: architecture_run",
        "version: working_tree",
        'recorded: "2026-08-01T10:00:00Z"',
        "environment: local_integrated",
        "verifier:",
        "  agent: verifier",
        "  provider: pml",
        "  model: verifier",
        "  effort: low",
        "targets: [architecture.durable_store]",
        "verdict: verified",
        "checks:",
        f"  - target: {original_obligation}",
        "    result: passed",
        "    method: agent_judgment",
        "    observation: The approved store preserves committed records.",
        "    reproduction: [Run the approved preservation check.]",
        "limitations: []",
        "",
    ]))
    assert ingest_report(
        report, product, definition, {}, definition_source=manifest
    ) == []

    definition["architecture"]["durable_store"]["constraints"][
        "recoverable_records"
    ] = {"statement": "The durable store MUST recover committed records."}
    bindings["architecture"]["durable_store"]["verification"][
        added_obligation
    ] = {"agent_judgment": 1.0}
    manifest.write_text(yaml.safe_dump(definition, sort_keys=False))
    (owner / "bindings.yaml").write_text(yaml.safe_dump(bindings, sort_keys=False))
    lock["definition"]["digest"] = canonical_hash(definition)
    lock["bindings"]["digest"] = bindings_digest(bindings)
    lock_path.write_text(yaml.safe_dump(lock, sort_keys=False))
    report_data = yaml.safe_load(report.read_text())
    report_data["checks"][0]["target"] = added_obligation
    report_data["checks"][0]["observation"] = "The approved store recovers committed records."
    report.write_text(yaml.safe_dump(report_data, sort_keys=False))

    assert ingest_report(
        report, product, definition, {}, definition_source=manifest
    ) == []
    state = yaml.safe_load(
        (metadata / "architecture" / "durable_store.state.yaml").read_text()
    )
    assert set(state["obligations"]) == {original_obligation, added_obligation}
    assert state["obligations"][added_obligation]["evidence"]["agent_judgment"]["result"] == "passed"
