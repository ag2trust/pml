"""Conformance checks for the versioned compiled-model contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args, get_type_hints

import pytest
from jsonschema import Draft202012Validator

from pml.compiled_model import (
    CompiledBehavior,
    CompiledFeature,
    CompiledModel,
    CompiledSignal,
    SignalOnlyDefinition,
    StatementDefinition,
    TriggerObligation,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "pml-compiled-model.schema.json"


def _model() -> dict[str, object]:
    behavior = "domains.notes.features.handling.behaviors.handle_note"
    feature = "domains.notes.features.handling"
    return {
        "format": "pml.compiled",
        "format_version": 1,
        "language_version": "0.1-draft",
        "definition_digest": "sha256:" + "0" * 64,
        "project": {
            "id": "sample",
            "name": "Sample",
            "purpose": "Handle notes.",
            "rule_obligations": [],
            "domains": ["domains.notes"],
        },
        "vocabulary": [],
        "actors": [{"id": "member", "meaning": "A member."}],
        "concepts": [{"id": "note", "meaning": "A note.", "states": []}],
        "architecture": [],
        "domains": [{"id": "notes", "path": "domains.notes", "purpose": "Manage notes.", "rule_obligations": [], "features": [feature]}],
        "features": [{"id": "handling", "path": feature, "domain": "domains.notes", "purpose": "Handle notes.", "actors": ["member"], "rule_obligations": [], "use_cases": [], "behaviors": [behavior], "related_to": [], "architecture": []}],
        "behaviors": [{"id": "handle_note", "path": behavior, "feature": feature, "trigger": {"kind": "direct", "case": {"obligation": behavior + ".trigger", "statement": "A member requests handling."}}, "completion_obligation": behavior + ".completion", "outcome": {"kind": "direct", "case": {"obligation": behavior + ".outcome", "statement": "The note is handled."}}, "failures": [], "rule_obligations": [], "related_to": [], "use_cases": []}],
        "use_cases": [],
        "signals": [],
        "relationships": [],
        "use_case_memberships": [],
        "obligations": [
            {"id": behavior + ".completion", "node": behavior, "kind": "completion", "definition": {"outcomes": [behavior + ".outcome"], "failures": []}},
            {"id": behavior + ".outcome", "node": behavior, "kind": "outcome", "definition": {"statement": "The note is handled."}},
            {"id": behavior + ".trigger", "node": behavior, "kind": "trigger", "definition": {"statement": "A member requests handling."}},
        ],
    }


def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _messages(errors: object) -> list[str]:
    """Flatten jsonschema branch errors so oneOf failures retain their cause."""

    messages: list[str] = []
    pending = list(errors)  # type: ignore[arg-type]
    while pending:
        error = pending.pop()
        messages.append(error.message)
        pending.extend(error.context)
    return messages


def test_schema_accepts_complete_v1_model() -> None:
    assert list(_validator().iter_errors(_model())) == []


def test_schema_accepts_every_v1_variant() -> None:
    model = _model()
    feature = "domains.notes.features.handling"
    behavior = feature + ".behaviors.handle_note"
    model["architecture"] = [{"id": "runtime", "path": "architecture.runtime", "category": "runtime", "selection": "Managed runtime.", "rationale": "A rationale.", "constraint_obligations": ["architecture.runtime.constraints.available"], "referenced_by": [feature]}]
    model["features"][0]["experience"] = {"surfaces": [{"id": "notes", "contains": [], "states": [{"id": "empty", "statements": []}], "accessibility": [], "responsive_behavior": []}]}  # type: ignore[index]
    model["features"][0]["architecture"] = ["architecture.runtime"]  # type: ignore[index]
    model["behaviors"][0]["conditions"] = {"statements": ["A condition."], "obligation": behavior + ".conditions"}  # type: ignore[index]
    model["behaviors"][0]["trigger"] = {"kind": "one_of", "cases": [{"id": "request", "obligation": behavior + ".trigger.request", "statement": "A request occurs."}, {"id": "ready", "obligation": behavior + ".trigger.ready", "signal": "note_ready"}]}  # type: ignore[index]
    model["behaviors"][0]["outcome"] = {"kind": "one_of", "exclusivity_obligation": behavior + ".outcome", "cases": [{"id": "handled", "obligation": behavior + ".outcome.handled", "statement": "The note is handled.", "signal": "note_done"}, {"id": "deferred", "obligation": behavior + ".outcome.deferred", "statement": "The note is deferred."}]}  # type: ignore[index]
    model["behaviors"][0]["failures"] = [{"id": "rejected", "obligation": behavior + ".failures.rejected", "statement": "The note is rejected.", "signal": "note_rejected"}]  # type: ignore[index]
    model["use_cases"] = [{"id": "handle", "path": feature + ".use_cases.handle", "feature": feature, "actor": "member", "goal": "Handle a note.", "behaviors": [behavior], "obligation": feature + ".use_cases.handle"}]
    model["signals"] = [{"id": "note_done", "meaning": "A note is done.", "subject": "note", "producer": {"behavior": behavior, "completion": behavior + ".outcome.handled"}, "consumers": [{"behavior": behavior, "trigger": behavior + ".trigger.ready"}]}]
    model["relationships"] = [{"kind": "related_to", "endpoints": [feature, behavior], "declared_by": [feature]}]
    model["use_case_memberships"] = [{"use_case": feature + ".use_cases.handle", "behavior": behavior}]
    model["obligations"] = [
        {"id": behavior + ".conditions", "node": behavior, "kind": "conditions", "definition": {"statements": ["A condition."]}},
        {"id": behavior + ".trigger.ready", "node": behavior, "kind": "trigger", "definition": {"signal": "note_ready"}},
        {"id": behavior + ".completion", "node": behavior, "kind": "completion", "definition": {"outcomes": [behavior + ".outcome.handled", behavior + ".outcome.deferred"], "failures": [behavior + ".failures.rejected"]}},
        {"id": behavior + ".outcome", "node": behavior, "kind": "outcome_exclusivity", "definition": {"alternatives": [behavior + ".outcome.handled", behavior + ".outcome.deferred"]}},
        {"id": behavior + ".outcome.handled", "node": behavior, "kind": "outcome", "definition": {"statement": "The note is handled.", "signal": "note_done"}},
        {"id": behavior + ".outcome.deferred", "node": behavior, "kind": "outcome", "definition": {"statement": "The note is deferred."}},
        {"id": behavior + ".failures.rejected", "node": behavior, "kind": "failure", "definition": {"statement": "The note is rejected.", "signal": "note_rejected"}},
        {"id": feature + ".rules.clear", "node": feature, "kind": "rule", "definition": {"statement": "Notes MUST be clear."}},
        {"id": feature + ".use_cases.handle", "node": feature, "kind": "use_case", "definition": {"actor": "member", "goal": "Handle a note.", "behaviors": [behavior]}},
        {"id": "architecture.runtime.constraints.available", "node": "architecture.runtime", "kind": "architecture_constraint", "definition": {"statement": "The runtime MUST be available."}},
    ]
    assert list(_validator().iter_errors(model)) == []


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda model: model.pop("signals"), "'signals' is a required property"),
        (lambda model: model.__setitem__("format_version", 2), "1 was expected"),
        (lambda model: model["project"].__setitem__("extra", "no"), "Additional properties are not allowed"),  # type: ignore[union-attr]
        (lambda model: model["features"][0].__setitem__("experience", None), "None is not of type 'object'"),  # type: ignore[index,union-attr]
        (lambda model: model["behaviors"][0]["trigger"].__setitem__("case", {"obligation": "x", "statement": "x", "signal": "s"}), "is not valid under any of the given schemas"),  # type: ignore[index,union-attr]
    ],
)
def test_schema_rejects_closed_or_invalid_v1_shape(mutate, expected: str) -> None:  # type: ignore[no-untyped-def]
    model = _model()
    mutate(model)
    assert any(expected in error.message for error in _validator().iter_errors(model))


@pytest.mark.parametrize("field", ["trigger", "outcome"])
@pytest.mark.parametrize("count", [1, 8])
def test_schema_rejects_one_of_case_counts_outside_approved_bounds(
    field: str, count: int
) -> None:
    model = _model()
    behavior = "domains.notes.features.handling.behaviors.handle_note"
    if field == "trigger":
        model["behaviors"][0][field] = {  # type: ignore[index]
            "kind": "one_of",
            "cases": [
                {"id": f"case_{index}", "obligation": f"{behavior}.trigger.case_{index}", "statement": "A request occurs."}
                for index in range(count)
            ],
        }
    else:
        model["behaviors"][0][field] = {  # type: ignore[index]
            "kind": "one_of",
            "exclusivity_obligation": behavior + ".outcome",
            "cases": [
                {"id": f"case_{index}", "obligation": f"{behavior}.outcome.case_{index}", "statement": "The note changes."}
                for index in range(count)
            ],
        }
    assert any(
        "is too short" in message or "is too long" in message
        for message in _messages(_validator().iter_errors(model))
    )


def test_shared_types_preserve_required_and_optional_contract_fields() -> None:
    model_hints = get_type_hints(CompiledModel)
    behavior_hints = get_type_hints(CompiledBehavior)
    feature_hints = get_type_hints(CompiledFeature)
    signal_hints = get_type_hints(CompiledSignal)

    assert CompiledModel.__required_keys__ == frozenset({
        "format", "format_version", "language_version", "definition_digest", "project",
        "vocabulary", "actors", "concepts", "architecture", "domains", "features",
        "behaviors", "use_cases", "signals", "relationships", "use_case_memberships", "obligations",
    })
    assert "experience" in feature_hints
    assert CompiledFeature.__optional_keys__ == frozenset({"experience"})
    assert CompiledBehavior.__optional_keys__ == frozenset({"conditions"})
    assert CompiledSignal.__optional_keys__ == frozenset({"subject"})
    assert "format_version" in model_hints and "trigger" in behavior_hints and "producer" in signal_hints


def test_shared_types_represent_signal_only_trigger_obligations() -> None:
    trigger_definition = get_type_hints(TriggerObligation)["definition"]

    assert set(get_args(trigger_definition)) == {StatementDefinition, SignalOnlyDefinition}
    assert SignalOnlyDefinition.__required_keys__ == frozenset({"signal"})
    assert SignalOnlyDefinition.__optional_keys__ == frozenset()
