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


def test_verification_report_matches_schema() -> None:
    schema = json.loads((ROOT / "schema" / "verification-report.schema.json").read_text())
    report = yaml.safe_load((ROOT / "examples" / "verification-report.yaml").read_text())
    assert list(Draft202012Validator(schema).iter_errors(report)) == []
