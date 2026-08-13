"""Golden-byte conformance for compiled-model v1 serialization."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from pml.compiled_model import CompiledModel
from pml.serialization import (
    _canonical_compiled_json_bytes,
    canonical_definition_bytes,
    definition_digest,
    serialize_compiled_model,
)
from pml.validator import load_document, validate_document


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "compiled_model"
COMPILED_SCHEMA = json.loads(
    (ROOT / "schema" / "pml-compiled-model.schema.json").read_text(encoding="utf-8")
)


def _compile(path: Path) -> tuple[dict[str, Any], CompiledModel]:
    document, loading_diagnostics = load_document(path)
    assert loading_diagnostics == []
    assert document is not None

    resolution = validate_document(document)
    assert resolution.diagnostics == ()
    assert resolution.compiled_model is not None
    assert list(
        Draft202012Validator(COMPILED_SCHEMA).iter_errors(resolution.compiled_model)
    ) == []
    return document, resolution.compiled_model


def _record(records: list[dict[str, Any]], key: str, value: str) -> dict[str, Any]:
    return next(record for record in records if record[key] == value)


def test_compiled_model_matches_the_complete_golden_byte_fixture() -> None:
    _, model = _compile(FIXTURES / "canonical.pml.yaml")
    expected = (FIXTURES / "canonical.json").read_bytes()

    assert serialize_compiled_model(model) == expected
    assert json.loads(expected) == model
    assert not expected.startswith(b"\xef\xbb\xbf")
    assert expected.endswith(b"\n")
    assert not expected.endswith(b"\n\n")
    assert b"\r" not in expected
    assert all(not line.endswith(b" ") for line in expected.splitlines())


def test_layout_and_escape_spellings_match_the_small_golden_byte_fixture() -> None:
    value = json.loads((FIXTURES / "layout.input.json").read_text(encoding="utf-8"))
    expected = (FIXTURES / "layout.json").read_bytes()

    assert _canonical_compiled_json_bytes(value) == expected
    assert b'"empty_array": []' in expected
    assert b'"empty_object": {}' in expected
    assert b'\\"' in expected
    assert b"\\\\" in expected
    assert b"\\b" in expected
    assert b"\\t" in expected
    assert b"\\n" in expected
    assert b"\\f" in expected
    assert b"\\r" in expected
    assert b"\\u001f" in expected
    assert b"/" in expected and b"\\/" not in expected
    assert "café".encode() in expected and b"\\u00e9" not in expected
    assert "🧭".encode() in expected and b"\\ud83e" not in expected


def test_authored_escape_sensitive_and_unicode_text_is_preserved_exactly() -> None:
    _, model = _compile(FIXTURES / "canonical.pml.yaml")
    encoded = serialize_compiled_model(model)

    assert model["project"]["purpose"] == (
        'Preserve "quotes", \\ paths, / solidus, \b backspace, \t tab, \n line feed, '
        "\f form feed, \r carriage return, \x1f unit separator, café, and 🧭."
    )
    assert b'\\"quotes\\"' in encoded
    assert b"\\\\ paths" in encoded
    assert b"/ solidus" in encoded and b"\\/ solidus" not in encoded
    for escape in (b"\\b", b"\\t", b"\\n", b"\\f", b"\\r", b"\\u001f"):
        assert escape in encoded
    assert "café".encode() in encoded
    assert "🧭".encode() in encoded


def test_reordered_monolithic_and_modular_inputs_are_byte_equivalent() -> None:
    monolithic_document, monolithic_model = _compile(
        FIXTURES / "canonical.pml.yaml"
    )
    modular_document, modular_model = _compile(FIXTURES / "modular")

    assert list(monolithic_document) != list(modular_document)
    assert monolithic_document == modular_document
    assert monolithic_model == modular_model
    assert serialize_compiled_model(monolithic_model) == serialize_compiled_model(
        modular_model
    )
    assert monolithic_model["definition_digest"] == modular_model["definition_digest"]


def test_map_materialized_and_derived_arrays_use_their_total_sort_keys() -> None:
    _, model = _compile(FIXTURES / "canonical.pml.yaml")

    for collection, key in (
        ("vocabulary", "term"),
        ("actors", "id"),
        ("concepts", "id"),
        ("architecture", "path"),
        ("domains", "path"),
        ("features", "path"),
        ("behaviors", "path"),
        ("use_cases", "path"),
        ("signals", "id"),
        ("obligations", "id"),
    ):
        values = [record[key] for record in model[collection]]
        assert values == sorted(values), collection

    feature = _record(model["features"], "id", "workspace")
    surfaces = feature["experience"]["surfaces"]
    assert [surface["id"] for surface in surfaces] == ["a_workspace", "z_empty_lists"]
    assert [state["id"] for state in surfaces[0]["states"]] == ["a_empty", "z_ready"]

    behavior = _record(model["behaviors"], "id", "a_start")
    assert [case["id"] for case in behavior["trigger"]["cases"]] == [
        "a_request",
        "z_ready",
    ]
    assert [case["id"] for case in behavior["outcome"]["cases"]] == [
        "a_saved",
        "z_saved",
    ]
    assert [failure["id"] for failure in behavior["failures"]] == [
        "a_rejected",
        "z_timeout",
    ]

    assert model["project"]["rule_obligations"] == sorted(
        model["project"]["rule_obligations"]
    )
    assert model["project"]["domains"] == sorted(model["project"]["domains"])
    for decision in model["architecture"]:
        assert decision["constraint_obligations"] == sorted(
            decision["constraint_obligations"]
        )
        assert decision["referenced_by"] == sorted(decision["referenced_by"])
    for domain in model["domains"]:
        assert domain["rule_obligations"] == sorted(domain["rule_obligations"])
        assert domain["features"] == sorted(domain["features"])
    for item in model["features"]:
        assert item["rule_obligations"] == sorted(item["rule_obligations"])
        assert item["use_cases"] == sorted(item["use_cases"])
        assert item["behaviors"] == sorted(item["behaviors"])
    for item in model["behaviors"]:
        assert item["rule_obligations"] == sorted(item["rule_obligations"])
        assert item["use_cases"] == sorted(item["use_cases"])
    for signal in model["signals"]:
        keys = [(item["behavior"], item["trigger"]) for item in signal["consumers"]]
        assert keys == sorted(keys)

    relationship_keys = []
    for relationship in model["relationships"]:
        assert relationship["endpoints"] == sorted(relationship["endpoints"])
        assert relationship["declared_by"] == sorted(relationship["declared_by"])
        relationship_keys.append(tuple(relationship["endpoints"]))
    assert relationship_keys == sorted(relationship_keys)

    membership_keys = [
        (membership["use_case"], membership["behavior"])
        for membership in model["use_case_memberships"]
    ]
    assert membership_keys == sorted(membership_keys)

    for obligation in model["obligations"]:
        definition = obligation["definition"]
        if obligation["kind"] == "completion":
            assert definition["outcomes"] == sorted(definition["outcomes"])
            assert definition["failures"] == sorted(definition["failures"])
        elif obligation["kind"] == "outcome_exclusivity":
            assert definition["alternatives"] == sorted(definition["alternatives"])


def test_authored_sequence_arrays_retain_source_order() -> None:
    _, model = _compile(FIXTURES / "canonical.pml.yaml")
    feature = _record(model["features"], "id", "workspace")
    behavior = _record(model["behaviors"], "id", "a_start")
    use_case = _record(model["use_cases"], "id", "z_flow")
    vocabulary = _record(model["vocabulary"], "term", "éclair")
    concept = _record(model["concepts"], "id", "a_record")
    surface = _record(feature["experience"]["surfaces"], "id", "a_workspace")
    state = _record(surface["states"], "id", "z_ready")

    assert vocabulary["forbidden_synonyms"] == ["later_term", "earlier_term"]
    assert concept["states"] == ["ready", "draft"]
    assert feature["actors"] == ["zed", "ada"]
    assert feature["architecture"] == ["architecture.z_runtime", "architecture.a_store"]
    assert feature["related_to"] == [
        "domains.z_archive.features.archive",
        "domains.a_work.features.workspace.behaviors.z_finish",
    ]
    assert behavior["related_to"] == [
        "domains.z_archive.features.archive",
        "domains.a_work.features.workspace.behaviors.z_finish",
    ]
    assert surface["contains"] == ["The primary action.", "The record status."]
    assert surface["accessibility"] == ["Announce the result.", "Identify the action."]
    assert surface["responsive_behavior"] == [
        "Keep the action visible.",
        "Keep the status readable.",
    ]
    assert state["statements"] == [
        "The ready state is visible.",
        "The next action is visible.",
    ]
    assert behavior["conditions"]["statements"] == [
        "The participant may create a record.",
        "The workspace accepts new records.",
    ]
    assert use_case["behaviors"] == [
        "domains.a_work.features.workspace.behaviors.z_finish",
        "domains.a_work.features.workspace.behaviors.a_start",
    ]

    condition_obligation = _record(
        model["obligations"],
        "id",
        "domains.a_work.features.workspace.behaviors.a_start.conditions",
    )
    use_case_obligation = _record(model["obligations"], "id", use_case["path"])
    assert condition_obligation["definition"]["statements"] == behavior["conditions"][
        "statements"
    ]
    assert use_case_obligation["definition"]["behaviors"] == use_case["behaviors"]


def test_architecture_references_are_resolved_without_reordering_authored_refs() -> None:
    _, model = _compile(FIXTURES / "canonical.pml.yaml")
    store = _record(model["architecture"], "id", "a_store")
    workspace = _record(model["features"], "id", "workspace")
    archive = _record(model["features"], "id", "archive")

    assert workspace["architecture"] == ["architecture.z_runtime", "architecture.a_store"]
    assert archive["architecture"] == ["architecture.a_store"]
    assert store["referenced_by"] == [
        "domains.a_work.features.workspace",
        "domains.z_archive.features.archive",
    ]
    assert store["constraint_obligations"] == [
        "architecture.a_store.constraints.a_recovery",
        "architecture.a_store.constraints.z_retention",
    ]


def test_definition_digest_has_independent_compact_bytes_and_digest_goldens() -> None:
    document, model = _compile(FIXTURES / "definition-digest.pml.yaml")
    expected_bytes = bytes.fromhex(
        (FIXTURES / "definition-digest.hex").read_text(encoding="ascii")
    )
    expected_digest = (FIXTURES / "definition-digest.sha256").read_text(
        encoding="ascii"
    ).strip()

    assert canonical_definition_bytes(document) == expected_bytes
    assert definition_digest(document) == expected_digest
    assert model["definition_digest"] == expected_digest
    assert "sha256:" + hashlib.sha256(expected_bytes).hexdigest() == expected_digest
    assert not expected_bytes.endswith(b"\n")
    assert b"/" in expected_bytes and b"\\/" not in expected_bytes
    assert b"\\n" in expected_bytes
    assert b'\\"mark\\"' in expected_bytes
    assert b"\\\\" in expected_bytes
    assert "café".encode() in expected_bytes
