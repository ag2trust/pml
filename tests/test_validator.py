from pathlib import Path

import copy
import json
from jsonschema import Draft202012Validator
import pytest
import yaml

from pml.formats import FORMAT_CHECKER
from pml.validator import validate_file


ROOT = Path(__file__).resolve().parents[1]


def test_project_manifest_is_valid() -> None:
    assert validate_file(ROOT / "pml.yaml") == []


def test_assistant_creation_example_is_valid() -> None:
    assert validate_file(ROOT / "examples" / "assistant-creation.pml.yaml") == []


def test_minimal_example_is_valid() -> None:
    assert validate_file(ROOT / "examples" / "minimal.pml.yaml") == []


@pytest.mark.parametrize(
    "example",
    ["behavior-direct-output.pml.yaml", "behavior-one-of-output.pml.yaml"],
)
def test_behavior_output_examples_are_valid(example: str) -> None:
    assert validate_file(ROOT / "examples" / example) == []


def test_architecture_decisions_example_is_valid() -> None:
    assert validate_file(ROOT / "examples" / "architecture-decisions.pml.yaml") == []


def test_invalid_architecture_example_has_required_diagnostics() -> None:
    diagnostics = validate_file(ROOT / "examples" / "architecture-invalid.pml.yaml")
    assert {item.code for item in diagnostics} >= {
        "schema",
        "unreferenced-architecture",
        "implementation-detail",
    }


def test_malformed_architecture_registry_returns_schema_diagnostics(
    tmp_path: Path,
) -> None:
    source = (ROOT / "examples" / "minimal.pml.yaml").read_text().replace(
        "domains:\n", "architecture: []\ndomains:\n", 1
    )
    manifest = tmp_path / "malformed-architecture.pml.yaml"
    manifest.write_text(source)

    diagnostics = validate_file(manifest)

    assert any(item.code == "schema" and item.path == "architecture" for item in diagnostics)


def test_malformed_node_architecture_value_returns_schema_diagnostics(
    tmp_path: Path,
) -> None:
    source = (ROOT / "examples" / "minimal.pml.yaml").read_text().replace(
        "        actors:\n",
        "        architecture: [[invalid]]\n        actors:\n",
        1,
    )
    manifest = tmp_path / "malformed-node-architecture.pml.yaml"
    manifest.write_text(source)

    diagnostics = validate_file(manifest)

    assert any(item.code == "schema" and "architecture" in item.path for item in diagnostics)


def test_invalid_example_has_documented_diagnostics() -> None:
    diagnostics = validate_file(ROOT / "examples" / "invalid.pml.yaml")
    actual = "\n".join(item.format() for item in diagnostics) + "\n"
    expected = (ROOT / "examples" / "invalid.expected.txt").read_text()
    assert actual == expected


def test_rejects_unknown_structure(tmp_path: Path) -> None:
    manifest = tmp_path / "invalid.yaml"
    manifest.write_text(
        """\
pml: 0.1-draft
project:
  id: sample
  name: Sample
  purpose: Sample product.
domains:
  sample:
    purpose: Sample domain.
    features: {}
invented_section: true
"""
    )
    diagnostics = validate_file(manifest)
    assert any(item.code == "schema" and "invented_section" in item.message for item in diagnostics)


def test_rejects_ambiguous_normative_language(tmp_path: Path) -> None:
    source = (ROOT / "pml.yaml").read_text().replace(
        "An Authoring Agent MUST use only language-defined sections and fields.",
        "An Authoring Agent should properly use language-defined sections and fields.",
    )
    manifest = tmp_path / "ambiguous.yaml"
    manifest.write_text(source)
    codes = {item.code for item in validate_file(manifest)}
    assert "non-normative" in codes
    assert "ambiguous-language" in codes


def test_rejects_undefined_actor(tmp_path: Path) -> None:
    source = (ROOT / "pml.yaml").read_text().replace(
        "actor: authoring_agent", "actor: unknown_actor", 1
    )
    manifest = tmp_path / "undefined.yaml"
    manifest.write_text(source)
    assert any(item.code == "undefined-reference" for item in validate_file(manifest))


def test_validates_directory_with_path_derived_mounting(tmp_path: Path) -> None:
    (tmp_path / "index.pml.yaml").write_text(
        """\
pml: 0.1-draft
project:
  id: sample
  name: Sample
  purpose: Sample product.
"""
    )
    (tmp_path / "actors.pml.yaml").write_text(
        """\
someone:
  meaning: Any participant.
"""
    )
    feature_dir = tmp_path / "domains" / "core" / "features"
    feature_dir.mkdir(parents=True)
    (tmp_path / "domains" / "core" / "index.pml.yaml").write_text(
        "purpose: Sample domain.\n"
    )
    (feature_dir / "sample.pml.yaml").write_text(
        """\
purpose: Sample feature.
rules:
  only:
    statement: THE SYSTEM MUST accept the input.
use_cases:
  run:
    actor: someone
    goal: Run.
    given: [Ready.]
    when: [Runs.]
    then: [Done.]
"""
    )
    assert validate_file(tmp_path) == []


def test_rejects_conflicting_fragments(tmp_path: Path) -> None:
    (tmp_path / "index.pml.yaml").write_text("project:\n  purpose: One.\n")
    (tmp_path / "project.pml.yaml").write_text("purpose: Two.\n")
    diagnostics = validate_file(tmp_path)
    assert any(item.code == "conflict" and "project.purpose" in item.message for item in diagnostics)


def _behavior_manifest(tmp_path: Path, behavior: dict, name: str = "behavior") -> Path:
    document = yaml.safe_load((ROOT / "examples" / "minimal.pml.yaml").read_text())
    feature = document["domains"]["notes"]["features"]["creation"]
    feature["behaviors"] = {"note_decision": behavior}
    manifest = tmp_path / f"{name}.pml.yaml"
    manifest.write_text(yaml.safe_dump(document, sort_keys=False))
    return manifest


def test_rejects_behavior_nesting(tmp_path: Path) -> None:
    manifest = tmp_path / "deep.pml.yaml"
    manifest.write_text(
        """\
pml: 0.1-draft
project:
  id: sample
  name: Sample
  purpose: Sample product.
domains:
  core:
    purpose: Sample domain.
    features:
      sample:
        purpose: Sample feature.
        rules:
          only:
            statement: THE SYSTEM MUST accept the input.
        use_cases:
          run:
            actor: someone
            goal: Run.
            given: [Ready.]
            when: [Runs.]
            then: [Done.]
        behaviors:
          level_one:
            output:
              statement: One visible level-one result.
            behaviors:
              level_two:
                output:
                  statement: One visible level-two result.
"""
    )
    diagnostics = validate_file(manifest)
    assert any(item.code == "schema" and "behaviors" in item.message for item in diagnostics)


@pytest.mark.parametrize("legacy_key", ["purpose", "inputs", "outputs", "emits"])
def test_rejects_legacy_behavior_keys(tmp_path: Path, legacy_key: str) -> None:
    values = {
        "purpose": "Legacy purpose.",
        "inputs": ["Legacy input."],
        "outputs": ["Legacy output."],
        "emits": ["legacy_signal"],
    }
    behavior = {
        "output": {"statement": "One visible Note result."},
        legacy_key: values[legacy_key],
    }

    diagnostics = validate_file(_behavior_manifest(tmp_path, behavior, legacy_key))

    assert any(
        item.code == "schema" and legacy_key in item.message for item in diagnostics
    )


def test_rejects_legacy_components_key(tmp_path: Path) -> None:
    document = yaml.safe_load((ROOT / "examples" / "minimal.pml.yaml").read_text())
    feature = document["domains"]["notes"]["features"]["creation"]
    feature["components"] = {
        "legacy": {"purpose": "Legacy component.", "outputs": ["Legacy result."]}
    }
    manifest = tmp_path / "components.pml.yaml"
    manifest.write_text(yaml.safe_dump(document, sort_keys=False))

    diagnostics = validate_file(manifest)

    assert any(
        item.code == "schema" and "components" in item.message
        for item in diagnostics
    )


def test_behavior_requires_output(tmp_path: Path) -> None:
    diagnostics = validate_file(_behavior_manifest(tmp_path, {}, "missing-output"))

    assert any(
        item.code == "schema" and "'output' is a required property" in item.message
        for item in diagnostics
    )


def test_rejects_mixed_direct_and_one_of_output(tmp_path: Path) -> None:
    behavior = {
        "output": {
            "statement": "One direct result.",
            "one_of": {
                "accepted": {"statement": "One accepted result."},
                "rejected": {"statement": "One rejected result."},
            },
        }
    }

    diagnostics = validate_file(_behavior_manifest(tmp_path, behavior, "mixed-output"))

    assert any(item.code == "schema" and item.path.endswith(".output") for item in diagnostics)


def test_rejects_one_case_one_of_output(tmp_path: Path) -> None:
    behavior = {
        "output": {
            "one_of": {"accepted": {"statement": "One accepted result."}}
        }
    }

    diagnostics = validate_file(_behavior_manifest(tmp_path, behavior, "one-case"))

    assert any(
        item.code == "schema" and item.path.endswith(".output")
        for item in diagnostics
    )


def test_rejects_unresolved_output_signal(tmp_path: Path) -> None:
    behavior = {
        "output": {
            "statement": "One visible Note result.",
            "emits": ["missing_signal"],
        }
    }

    diagnostics = validate_file(_behavior_manifest(tmp_path, behavior, "missing-signal"))

    assert any(
        item.code == "undefined-reference"
        and item.path.endswith(".behaviors.note_decision.output.emits")
        for item in diagnostics
    )


def test_output_statement_rejects_ambiguity_without_requiring_must(tmp_path: Path) -> None:
    behavior = {"output": {"statement": "One properly visible Note result."}}

    diagnostics = validate_file(_behavior_manifest(tmp_path, behavior, "ambiguous-output"))

    assert "ambiguous-language" in {item.code for item in diagnostics}
    assert "non-normative" not in {item.code for item in diagnostics}


def test_output_statement_rejects_implementation_detail(tmp_path: Path) -> None:
    behavior = {
        "output": {"statement": "The save_note() function returns one Note result."}
    }

    diagnostics = validate_file(_behavior_manifest(tmp_path, behavior, "implementation-output"))

    assert "implementation-detail" in {item.code for item in diagnostics}
    assert "non-normative" not in {item.code for item in diagnostics}


@pytest.mark.parametrize(
    "implementation_detail",
    [
        "filenames",
        "functions",
        "classes",
        "endpoints",
        "framework elements",
        "libraries",
        "tests",
        "payload schemas",
    ],
)
def test_output_statement_rejects_plural_implementation_details(
    tmp_path: Path,
    implementation_detail: str,
) -> None:
    behavior = {
        "output": {
            "statement": f"One result produced through prescribed {implementation_detail}."
        }
    }

    diagnostics = validate_file(
        _behavior_manifest(tmp_path, behavior, f"plural-{implementation_detail.split()[0]}")
    )

    assert "implementation-detail" in {item.code for item in diagnostics}
    assert "non-normative" not in {item.code for item in diagnostics}


def test_output_alternative_named_output_is_normative_by_position(
    tmp_path: Path,
) -> None:
    behavior = {
        "output": {
            "one_of": {
                "output": {"statement": "One visible Note result."},
                "failure": {"statement": "One visible failure result."},
            }
        }
    }

    diagnostics = validate_file(
        _behavior_manifest(tmp_path, behavior, "output-alternative")
    )

    assert diagnostics == []


def test_non_output_statements_named_output_still_require_normative_markers(
    tmp_path: Path,
) -> None:
    document = yaml.safe_load((ROOT / "examples" / "minimal.pml.yaml").read_text())
    feature = document["domains"]["notes"]["features"]["creation"]
    feature["rules"]["output"] = {"statement": "A visible rule result."}
    document["signals"] = {
        "note_changed": {"meaning": "A Note has visibly changed."}
    }
    feature["reactions"] = {
        "output": {
            "on": "note_changed",
            "statement": "A visible reaction result.",
        }
    }
    document["architecture"] = {
        "approved_runtime": {
            "category": "runtime",
            "selection": "Approved runtime.",
            "rationale": "Owner approval is required to replace this runtime.",
            "constraints": {
                "output": {"statement": "A visible architecture result."}
            },
        }
    }
    feature["architecture"] = ["approved_runtime"]
    manifest = tmp_path / "non-output-statements.pml.yaml"
    manifest.write_text(yaml.safe_dump(document, sort_keys=False))

    diagnostics = validate_file(manifest)

    assert {
        item.path for item in diagnostics if item.code == "non-normative"
    } == {
        "domains.notes.features.creation.rules.output.statement",
        "domains.notes.features.creation.reactions.output.statement",
        "architecture.approved_runtime.constraints.output.statement",
    }


def test_rejects_overloaded_rule_map(tmp_path: Path) -> None:
    rules = "\n".join(
        f"""\
          rule_{index}:
            statement: THE SYSTEM MUST accept input {index}."""
        for index in range(8)
    )
    manifest = tmp_path / "overloaded.pml.yaml"
    manifest.write_text(
        f"""\
pml: 0.1-draft
project:
  id: sample
  name: Sample
  purpose: Sample product.
actors:
  someone:
    meaning: Any participant.
domains:
  core:
    purpose: Sample domain.
    features:
      sample:
        purpose: Sample feature.
        rules:
{rules}
        use_cases:
          run:
            actor: someone
            goal: Run.
            given: [Ready.]
            when: [Runs.]
            then: [Done.]
"""
    )
    diagnostics = validate_file(manifest)
    assert any(item.code == "schema" and "too many properties" in item.message for item in diagnostics)


def test_validates_signals_relationships_behaviors_and_architecture(tmp_path: Path) -> None:
    manifest = tmp_path / "connected.pml.yaml"
    manifest.write_text(
        """\
pml: "0.1-draft"
project:
  id: sample
  name: Sample
  purpose: Demonstrate connected behavior.
signals:
  payment_failed:
    meaning: A payment attempt did not complete.
architecture:
  durable_store:
    category: database
    selection: PostgreSQL
    rationale: Replacing the approved durable store requires Owner approval.
    constraints:
      preserve_concurrent_credits:
        statement: Concurrent credit changes MUST all survive.
domains:
  billing:
    purpose: Manage purchases.
    features:
      purchase:
        purpose: Purchase credits.
        related_to: [domains.billing.features.purchase.behaviors.payment]
        behaviors:
          payment:
            context: [A payment authorization.]
            output:
              statement: One complete payment result.
              emits: [payment_failed]
            related_to: [domains.billing.features.purchase.behaviors.balance]
          balance:
            output:
              statement: One current available-credit balance.
            architecture: [durable_store]
            reactions:
              preserve_balance:
                on: payment_failed
                statement: The existing balance MUST remain unchanged.
"""
    )
    assert validate_file(manifest) == []


def test_rejects_unknown_signal_relationship_and_architecture(tmp_path: Path) -> None:
    source = (ROOT / "examples" / "minimal.pml.yaml").read_text().replace(
        "        rules:\n",
        "        emits: [missing_signal]\n"
        "        related_to: [domains.notes.features.missing]\n"
        "        architecture: [missing_decision]\n"
        "        rules:\n",
        1,
    )
    manifest = tmp_path / "unknown-references.pml.yaml"
    manifest.write_text(source)
    diagnostics = validate_file(manifest)
    assert sum(item.code == "undefined-reference" for item in diagnostics) == 3


def test_architecture_requires_bottom_up_references_and_rejects_implementation_detail(tmp_path: Path) -> None:
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
    )
    manifest = tmp_path / "unreferenced.pml.yaml"
    manifest.write_text(source)
    diagnostics = validate_file(manifest)
    assert any(item.code == "unreferenced-architecture" for item in diagnostics)

    manifest.write_text(source.replace(
        "        actors:\n",
        "        architecture: [approved_runtime]\n        actors:\n",
        1,
    ).replace("Approved runtime.", "runtime.py"))
    diagnostics = validate_file(manifest)
    assert any(item.code == "implementation-detail" for item in diagnostics)

    manifest.write_text(source.replace(
        "        actors:\n",
        "        architecture: [approved_runtime]\n        actors:\n",
        1,
    ).replace("Approved runtime.", "Node.js (LTS)"))
    assert validate_file(manifest) == []

    manifest.write_text(source.replace(
        "        actors:\n",
        "        architecture: [approved_runtime]\n        actors:\n",
        1,
    ).replace("Approved runtime.", "initializeRuntime()"))
    diagnostics = validate_file(manifest)
    assert any(item.code == "implementation-detail" for item in diagnostics)

    manifest.write_text(source.replace(
        "        actors:\n",
        "        architecture: [approved_runtime]\n        actors:\n",
        1,
    ).replace("Approved runtime.", "DATABASE_URL=approved"))
    diagnostics = validate_file(manifest)
    assert any(item.code == "implementation-detail" for item in diagnostics)

    manifest.write_text(source.replace(
        "        actors:\n",
        "        architecture: [approved_runtime]\n        actors:\n",
        1,
    ).replace("Approved runtime.", "'DATABASE_HOST: database.internal'"))
    diagnostics = validate_file(manifest)
    assert any(item.code == "implementation-detail" for item in diagnostics)

    referenced_source = source.replace(
        "        actors:\n",
        "        architecture: [approved_runtime]\n        actors:\n",
        1,
    )
    for field in (
        "selection: Approved runtime.",
        "rationale: Owner approval is required to replace this runtime.",
        "statement: The runtime MUST preserve portable execution.",
    ):
        manifest.write_text(referenced_source.replace(
            field,
            field.split(":", 1)[0]
            + ': \'{"host": "database.internal", "port": 5432}\'',
        ))
        diagnostics = validate_file(manifest)
        assert any(item.code == "implementation-detail" for item in diagnostics)


def test_architecture_rejects_inline_definitions_and_unknown_categories(tmp_path: Path) -> None:
    source = (ROOT / "examples" / "minimal.pml.yaml").read_text().replace(
        "        actors:\n",
        """        architecture:
          category: invented
          selection: Inline selection.
          rationale: Inline rationale.
        actors:
""",
        1,
    )
    manifest = tmp_path / "inline.pml.yaml"
    manifest.write_text(source)
    messages = "\n".join(item.message for item in validate_file(manifest))
    assert "architecture" in messages


def test_verification_report_matches_schema() -> None:
    schema = json.loads((ROOT / "schema" / "verification-report.schema.json").read_text())
    report = yaml.safe_load((ROOT / "examples" / "verification-report.yaml").read_text())
    assert list(Draft202012Validator(schema).iter_errors(report)) == []


def test_invalid_verification_report_fails_schema() -> None:
    schema = json.loads((ROOT / "schema" / "verification-report.schema.json").read_text())
    report = yaml.safe_load(
        (ROOT / "examples" / "invalid-verification-report.yaml").read_text()
    )

    assert list(Draft202012Validator(schema).iter_errors(report))


def test_verification_report_allows_implementation_without_checks() -> None:
    schema = json.loads((ROOT / "schema" / "verification-report.schema.json").read_text())
    report = yaml.safe_load((ROOT / "examples" / "verification-report.yaml").read_text())
    del report["checks"]

    assert list(Draft202012Validator(schema).iter_errors(report)) == []


def test_verification_report_rejects_empty_evidence_sections_and_bounds() -> None:
    schema = json.loads((ROOT / "schema" / "verification-report.schema.json").read_text())
    report = yaml.safe_load((ROOT / "examples" / "verification-report.yaml").read_text())
    validator = Draft202012Validator(schema)

    empty = copy.deepcopy(report)
    del empty["implementation"]
    del empty["checks"]

    unknown_status = copy.deepcopy(report)
    unknown_status["implementation"][0]["status"] = "complete"

    too_many_targets = copy.deepcopy(report)
    too_many_targets["targets"] = [f"target_{index}" for index in range(65)]

    too_many_implementations = copy.deepcopy(report)
    too_many_implementations["implementation"] *= 65

    too_many_checks = copy.deepcopy(report)
    too_many_checks["checks"] *= 257

    too_many_reproduction_steps = copy.deepcopy(report)
    too_many_reproduction_steps["checks"][1]["reproduction"] = ["step"] * 33

    oversized_text = copy.deepcopy(report)
    oversized_text["implementation"][0]["observation"] = "x" * 4097

    for invalid in (
        empty,
        unknown_status,
        too_many_targets,
        too_many_implementations,
        too_many_checks,
        too_many_reproduction_steps,
        oversized_text,
    ):
        assert list(validator.iter_errors(invalid))

    many_artifacts = copy.deepcopy(report)
    many_artifacts["checks"][0]["evidence"] = [
        f"artifact_{index}" for index in range(65)
    ]
    assert list(validator.iter_errors(many_artifacts)) == []


def test_verification_report_enforces_ids_utc_and_closed_check_types() -> None:
    schema = json.loads((ROOT / "schema" / "verification-report.schema.json").read_text())
    report = yaml.safe_load((ROOT / "examples" / "verification-report.yaml").read_text())
    validator = Draft202012Validator(schema, format_checker=FORMAT_CHECKER)

    invalid_report_id = copy.deepcopy(report)
    invalid_report_id["verification"] = "verification-example"

    invalid_probe_id = copy.deepcopy(report)
    invalid_probe_id["checks"][0]["probe"] = "assistant-ownership"

    non_utc_recorded = copy.deepcopy(report)
    non_utc_recorded["recorded"] = "2026-07-22T06:00:00-04:00"

    invalid_recorded = copy.deepcopy(report)
    invalid_recorded["recorded"] = "2026-02-30T12:00:00Z"

    irrelevant_probe = copy.deepcopy(report)
    irrelevant_probe["checks"][1]["probe"] = "assistant_ownership"

    irrelevant_attester = copy.deepcopy(report)
    irrelevant_attester["checks"][0]["attester"] = "Owner"

    irrelevant_reproduction = copy.deepcopy(report)
    irrelevant_reproduction["checks"][0]["reproduction"] = ["Run it."]

    irrelevant_evidence = copy.deepcopy(report)
    irrelevant_evidence["checks"][1]["evidence"] = ["artifact.json"]

    for invalid in (
        invalid_report_id,
        invalid_probe_id,
        non_utc_recorded,
        invalid_recorded,
        irrelevant_probe,
        irrelevant_attester,
        irrelevant_reproduction,
        irrelevant_evidence,
    ):
        assert list(validator.iter_errors(invalid))
