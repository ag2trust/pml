from pathlib import Path

import json
from jsonschema import Draft202012Validator
import yaml

from pml.validator import validate_file


ROOT = Path(__file__).resolve().parents[1]


def test_project_manifest_is_valid() -> None:
    assert validate_file(ROOT / "pml.yaml") == []


def test_assistant_creation_example_is_valid() -> None:
    assert validate_file(ROOT / "examples" / "assistant-creation.pml.yaml") == []


def test_minimal_example_is_valid() -> None:
    assert validate_file(ROOT / "examples" / "minimal.pml.yaml") == []


def test_architecture_decisions_example_is_valid() -> None:
    assert validate_file(ROOT / "examples" / "architecture-decisions.pml.yaml") == []


def test_invalid_architecture_example_has_required_diagnostics() -> None:
    diagnostics = validate_file(ROOT / "examples" / "architecture-invalid.pml.yaml")
    assert {item.code for item in diagnostics} >= {
        "schema",
        "unreferenced-architecture",
        "implementation-detail",
    }


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


def test_rejects_component_nesting(tmp_path: Path) -> None:
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
        components:
          level_one:
            purpose: Level one.
            components:
              level_two:
                purpose: Level two.
                components:
                  level_three:
                    purpose: Too deep.
"""
    )
    diagnostics = validate_file(manifest)
    assert any(item.code == "schema" and "components" in item.message for item in diagnostics)


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


def test_validates_signals_relationships_components_and_architecture(tmp_path: Path) -> None:
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
        components:
          payment:
            purpose: Determine the payment result.
            inputs: [A payment authorization.]
            outputs: [A payment result.]
            emits: [payment_failed]
            related_to: [domains.billing.features.purchase.components.balance]
          balance:
            purpose: Maintain available credits.
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
