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
    StepOutcome,
    evaluate_cli_expectations,
    evaluate_http_expectations,
    load_probes,
    missing_probe_diagnostics,
    probe_fingerprint,
    run_probe,
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


@pytest.mark.parametrize(
    ("step", "key", "value"),
    [
        ("http", "status_not", 404),
        ("http", "body_lacks", ["rating"]),
        ("http", "text_has", ["Assistant"]),
        ("http", "text_lacks", ["numeric rating"]),
        ("cli", "stdout_lacks", ["warning"]),
    ],
)
def test_probe_schema_accepts_negative_and_text_expectations(
    step: str, key: str, value: object
) -> None:
    schema = json.loads((ROOT / "schema" / "pml-probe.schema.json").read_text())
    probe = {
        "pml_probe": "0.1",
        "probe": "expectations",
        "verifies": "domains.notes.features.creation.rules.preserve_content",
        "env": "staging",
        "steps": [{
            step: "GET /notes" if step == "http" else ["notes", "verify-content"],
            "expect": {key: value},
        }],
    }

    assert Draft202012Validator(schema).is_valid(probe)


def test_probe_schema_rejects_status_and_status_not_together() -> None:
    schema = json.loads((ROOT / "schema" / "pml-probe.schema.json").read_text())
    probe = {
        "pml_probe": "0.1",
        "probe": "ambiguous_status",
        "verifies": "domains.notes.features.creation.rules.preserve_content",
        "env": "staging",
        "steps": [{
            "http": "GET /notes",
            "expect": {"status": 200, "status_not": 404},
        }],
    }

    assert not Draft202012Validator(schema).is_valid(probe)


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


def test_probe_setup_captures_are_visible_to_steps(tmp_path: Path) -> None:
    definition = minimal_definition()
    probe = tmp_path / "with-setup.probe.yaml"
    probe.write_text(
        """\
pml_probe: "0.1"
probe: with_setup
verifies: domains.notes.features.creation.rules.preserve_content
env: staging
setup:
  - http: POST /notes
    as: member
    expect: {status: 201, body_has: [id]}
    capture: {note_id: body.id}
steps:
  - http: GET /notes/{note_id}
    as: member
    expect: {status: 200}
"""
    )

    probes, diagnostics = load_probes(probe, definition)

    assert diagnostics == []
    assert list(probes) == ["with_setup"]
    assert probes["with_setup"]["setup"][0]["capture"] == {"note_id": "body.id"}


def test_probe_setup_rejects_unknown_actor_and_forward_variable(
    tmp_path: Path,
) -> None:
    definition = minimal_definition()
    probe = tmp_path / "invalid-setup.probe.yaml"
    probe.write_text(
        """\
pml_probe: "0.1"
probe: invalid_setup
verifies: domains.notes.features.creation.rules.preserve_content
env: staging
setup:
  - http: GET /notes/{note_id}
    as: stranger
    expect: {status: 200}
steps:
  - session: reset
"""
    )

    _, diagnostics = load_probes(probe, definition)

    assert {item.code for item in diagnostics} == {
        "undefined-variable",
        "undefined-reference",
    }
    assert all("setup[0]" in item.path for item in diagnostics)


def test_probe_setup_duplicate_capture_across_setup_and_steps(
    tmp_path: Path,
) -> None:
    definition = minimal_definition()
    probe = tmp_path / "duplicate-capture.probe.yaml"
    probe.write_text(
        """\
pml_probe: "0.1"
probe: duplicate_capture
verifies: domains.notes.features.creation.rules.preserve_content
env: staging
setup:
  - http: POST /notes
    as: member
    expect: {status: 201, body_has: [id]}
    capture: {note_id: body.id}
steps:
  - http: POST /notes
    as: member
    expect: {status: 201, body_has: [id]}
    capture: {note_id: body.id}
"""
    )

    _, diagnostics = load_probes(probe, definition)

    assert [item.code for item in diagnostics] == ["duplicate-capture"]
    assert "steps[0].capture.note_id" in diagnostics[0].path


def test_probe_schema_accepts_maximum_setup_items(tmp_path: Path) -> None:
    definition = minimal_definition()
    setup_lines = "  - session: reset\n" * 32
    accepted = tmp_path / "accepted-setup.probe.yaml"
    accepted.write_text(
        f"""\
pml_probe: "0.1"
probe: accepted_setup
verifies: domains.notes.features.creation.rules.preserve_content
env: staging
setup:
{setup_lines}steps:
  - session: reset
"""
    )
    probes, diagnostics = load_probes(accepted, definition)
    assert diagnostics == []
    assert list(probes) == ["accepted_setup"]

    setup_lines = "  - session: reset\n" * 33
    rejected = tmp_path / "rejected-setup.probe.yaml"
    rejected.write_text(
        f"""\
pml_probe: "0.1"
probe: rejected_setup
verifies: domains.notes.features.creation.rules.preserve_content
env: staging
setup:
{setup_lines}steps:
  - session: reset
"""
    )
    probes, diagnostics = load_probes(rejected, definition)
    assert probes == {}
    assert [item.code for item in diagnostics] == ["schema"]
    assert "is too long" in diagnostics[0].message


def test_probe_schema_rejects_empty_setup(tmp_path: Path) -> None:
    definition = minimal_definition()
    probe = tmp_path / "empty-setup.probe.yaml"
    probe.write_text(
        """\
pml_probe: "0.1"
probe: empty_setup
verifies: domains.notes.features.creation.rules.preserve_content
env: staging
setup: []
steps:
  - session: reset
"""
    )
    probes, diagnostics = load_probes(probe, definition)
    assert probes == {}
    assert [item.code for item in diagnostics] == ["schema"]


def test_validate_probes_accepts_setup_block(tmp_path: Path) -> None:
    probe = tmp_path / "setup.probe.yaml"
    probe.write_text(
        """\
pml_probe: "0.1"
probe: preserve_content
verifies: domains.notes.features.creation.rules.preserve_content
env: staging
setup:
  - cli: [notes, seed]
    as: member
    expect: {exit: 0}
steps:
  - cli: [notes, verify-content]
    as: member
    expect: {exit: 0}
"""
    )
    assert main([
        "validate-probes",
        str(ROOT / "examples" / "minimal.pml.yaml"),
        str(probe),
        "--bindings",
        str(ROOT / "examples" / "bindings.yaml"),
        "--require-complete",
    ]) == 0


def test_verification_report_schema_accepts_inconclusive_probe_result() -> None:
    schema = json.loads(
        (ROOT / "schema" / "verification-report.schema.json").read_text()
    )
    assert "inconclusive" in schema["$defs"]["result"]["enum"]


def test_state_schema_accepts_inconclusive_probe_result() -> None:
    schema = json.loads((ROOT / "schema" / "pml-state.schema.json").read_text())
    assert "inconclusive" in schema["$defs"]["result"]["enum"]


def _probe_with_setup() -> dict:
    return {
        "pml_probe": "0.1",
        "probe": "runner_case",
        "verifies": "domains.notes.features.creation.rules.preserve_content",
        "env": "staging",
        "setup": [
            {
                "http": "POST /notes",
                "as": "member",
                "expect": {"status": 201, "body_has": ["id"]},
                "capture": {"note_id": "body.id"},
            }
        ],
        "steps": [
            {
                "http": "GET /notes/{note_id}",
                "as": "member",
                "expect": {"status": 200},
            }
        ],
    }


def test_run_probe_executes_setup_before_steps_and_threads_captures() -> None:
    probe = _probe_with_setup()
    executions: list[tuple[str, dict[str, str]]] = []

    def executor(step: dict, captures: dict[str, str]) -> StepOutcome:
        executions.append((step.get("http") or step.get("cli") or step["session"], dict(captures)))
        if step.get("capture"):
            return StepOutcome(True, "captured", {"note_id": "abc123"})
        return StepOutcome(True, "matched")

    result = run_probe(probe, executor)

    assert result.result == "passed"
    assert [call[0] for call in executions] == [
        "POST /notes",
        "GET /notes/{note_id}",
    ]
    assert executions[0][1] == {}
    assert executions[1][1] == {"note_id": "abc123"}
    assert [(report.section, report.index, report.ok) for report in result.steps] == [
        ("setup", 0, True),
        ("steps", 0, True),
    ]
    assert result.captures == {"note_id": "abc123"}


def test_run_probe_setup_failure_yields_inconclusive_and_skips_steps() -> None:
    probe = _probe_with_setup()
    executed_sections: list[str] = []

    def executor(step: dict, captures: dict[str, str]) -> StepOutcome:
        # First call is the setup step; force it to fail.
        if not executed_sections:
            executed_sections.append("setup")
            return StepOutcome(False, "status 500")
        executed_sections.append("steps")
        return StepOutcome(True, "matched")

    result = run_probe(probe, executor)

    assert result.result == "inconclusive"
    assert executed_sections == ["setup"]
    assert result.steps[0].section == "setup"
    assert result.steps[0].ok is False
    assert "setup step 0" in result.observation


def test_run_probe_step_failure_yields_failed() -> None:
    probe = _probe_with_setup()

    def executor(step: dict, captures: dict[str, str]) -> StepOutcome:
        if step.get("capture"):
            return StepOutcome(True, "captured", {"note_id": "abc123"})
        return StepOutcome(False, "status 500")

    result = run_probe(probe, executor)

    assert result.result == "failed"
    assert [report.ok for report in result.steps] == [True, False]
    assert "trigger step 0" in result.observation


@pytest.mark.parametrize(
    ("step", "fixture", "expected_result"),
    [
        (
            {"http": "GET /status", "expect": {"status_not": 404}},
            {"status": 200, "body_text": "{}"},
            "passed",
        ),
        (
            {"http": "GET /status", "expect": {"status_not": 404}},
            {"status": 404, "body_text": "{}"},
            "failed",
        ),
        (
            {"http": "GET /profile", "expect": {"body_lacks": ["rating"]}},
            {"status": 200, "body_text": '{"name":"Ada"}'},
            "passed",
        ),
        (
            {"http": "GET /profile", "expect": {"body_lacks": ["rating"]}},
            {"status": 200, "body_text": '{"rating":5}'},
            "failed",
        ),
        (
            {"http": "GET /page", "expect": {"text_has": ["Assistant"]}},
            {"status": 200, "body_text": "<h1>Assistant</h1>"},
            "passed",
        ),
        (
            {"http": "GET /page", "expect": {"text_has": ["Assistant"]}},
            {"status": 200, "body_text": "<h1>assistant</h1>"},
            "failed",
        ),
        (
            {"http": "GET /page", "expect": {"text_lacks": ["numeric rating"]}},
            {"status": 200, "body_text": "<h1>Assistant</h1>"},
            "passed",
        ),
        (
            {"http": "GET /page", "expect": {"text_lacks": ["numeric rating"]}},
            {"status": 200, "body_text": "<p>numeric rating: 5</p>"},
            "failed",
        ),
        (
            {"cli": ["notes", "verify"], "expect": {"stdout_lacks": ["warning"]}},
            {"exit_code": 0, "stdout": "verified"},
            "passed",
        ),
        (
            {"cli": ["notes", "verify"], "expect": {"stdout_lacks": ["warning"]}},
            {"exit_code": 0, "stdout": "warning: stale note"},
            "failed",
        ),
    ],
)
def test_run_probe_applies_negative_and_text_expectations_to_fixture_responses(
    step: dict, fixture: dict, expected_result: str
) -> None:
    probe = {
        "pml_probe": "0.1",
        "probe": "fixture_expectations",
        "verifies": "domains.notes.features.creation.rules.preserve_content",
        "env": "staging",
        "steps": [step],
    }

    def executor(step: dict, captures: dict[str, str]) -> StepOutcome:
        del captures
        if "http" in step:
            return evaluate_http_expectations(step["expect"], **fixture)
        return evaluate_cli_expectations(step["expect"], **fixture)

    result = run_probe(probe, executor)

    assert result.result == expected_result
    assert result.steps[0].ok is (expected_result == "passed")


def test_run_probe_without_setup_still_returns_passed() -> None:
    probe = {
        "pml_probe": "0.1",
        "probe": "no_setup",
        "verifies": "domains.notes.features.creation.rules.preserve_content",
        "env": "staging",
        "steps": [
            {"cli": ["notes", "verify"], "expect": {"exit": 0}},
        ],
    }
    result = run_probe(probe, lambda step, captures: StepOutcome(True, "ok"))
    assert result.result == "passed"
    assert len(result.steps) == 1


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
