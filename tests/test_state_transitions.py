"""Conformance coverage for completion-owned product state transitions."""

from __future__ import annotations

from pathlib import Path

import pytest

from pml.cli import main
from pml.validator import validate_document, validate_file


def _document(
    transitions: dict[str, str] | None = None,
    *,
    condition: str | None = None,
    states: list[str] | None = None,
) -> dict:
    behavior: dict[str, object] = {
        "trigger": {"statement": "A Member changes a Note."},
        "outcome": {"statement": "The Note changes."},
    }
    if transitions is not None:
        behavior["outcome"]["transitions"] = transitions  # type: ignore[index]
    if condition is not None:
        behavior["conditions"] = [{"concept": "note", "state": condition}]
    return {
        "pml": "0.1-draft",
        "project": {"id": "sample", "name": "Sample", "purpose": "Handle notes."},
        "concepts": {
            "note": {"meaning": "A Note.", "states": states or ["draft", "active"]}
        },
        "domains": {
            "notes": {
                "purpose": "Manage Notes.",
                "features": {"handling": {"purpose": "Handle a Note.", "behaviors": {"change": behavior}}},
            }
        },
    }


def _diagnostic_codes(document: dict) -> set[str]:
    return {diagnostic.code for diagnostic in validate_document(document).diagnostics}


def test_transition_rejects_unknown_concept() -> None:
    assert _diagnostic_codes(_document({"missing": "none -> draft"})) == {
        "PML-E-TRANSITION-CONCEPT"
    }


@pytest.mark.parametrize("transition", ["unknown -> active", "draft -> unknown", "draft -> draft"])
def test_transition_rejects_undeclared_or_identical_states(transition: str) -> None:
    diagnostics = validate_document(_document({"note": transition})).diagnostics

    assert [(diagnostic.code, diagnostic.severity) for diagnostic in diagnostics] == [
        ("PML-E-TRANSITION-STATE", "error")
    ]


def test_transition_map_accepts_at_most_three_concepts() -> None:
    document = _document({"note": "none -> draft"})
    document["concepts"].update(  # type: ignore[index]
        {
            "task": {"meaning": "A Task.", "states": ["draft"]},
            "message": {"meaning": "A Message.", "states": ["draft"]},
            "alert": {"meaning": "An Alert.", "states": ["draft"]},
        }
    )
    document["domains"]["notes"]["features"]["handling"]["behaviors"]["change"]["outcome"]["transitions"] = {  # type: ignore[index]
        "note": "none -> draft",
        "task": "none -> draft",
        "message": "none -> draft",
        "alert": "none -> draft",
    }

    assert "schema" in _diagnostic_codes(document)


@pytest.mark.parametrize(
    "state", ["*", "none", "draft -> review", "draft ->", "-> active", "draft\n"]
)
def test_concept_states_reserve_transition_sentinels_and_separator_boundaries(
    state: str,
) -> None:
    diagnostics = validate_document(_document(states=[state])).diagnostics

    assert any(
        item.code == "schema" and item.path == "concepts.note.states[0]"
        for item in diagnostics
    )


@pytest.mark.parametrize(
    "transition",
    ["draft -> active -> none", "draft\n -> active", "draft -> active\n"],
)
def test_transition_has_exactly_one_reserved_separator_and_no_line_breaks(
    transition: str,
) -> None:
    diagnostics = validate_document(_document({"note": transition})).diagnostics

    assert any(
        item.code == "schema"
        and item.path.endswith("outcome")
        for item in diagnostics
    )


def test_state_token_with_spaces_remains_a_transition_endpoint() -> None:
    document = _document({"note": "none -> in review"}, states=["in review", "active"])
    behaviors = document["domains"]["notes"]["features"]["handling"]["behaviors"]
    behaviors["activate"] = {
        "trigger": {"statement": "A Member activates a Note."},
        "outcome": {
            "statement": "The Note becomes active.",
            "transitions": {"note": "in review -> active"},
        },
    }
    behaviors["remove"] = {
        "trigger": {"statement": "A Member removes an active Note."},
        "outcome": {
            "statement": "The active Note ceases to exist.",
            "transitions": {"note": "active -> none"},
        },
    }

    assert validate_document(document).diagnostics == ()


def test_state_warnings_cover_unreachable_dead_end_and_unproduced_condition() -> None:
    diagnostics = validate_document(
        _document({"note": "none -> draft"}, condition="active")
    ).diagnostics

    assert [(item.path, item.code) for item in diagnostics] == [
        ("concepts.note.states[0]", "PML-W-STATE-DEAD-END"),
        ("concepts.note.states[1]", "PML-W-STATE-DEAD-END"),
        ("concepts.note.states[1]", "PML-W-STATE-UNREACHABLE"),
        (
            "domains.notes.features.handling.behaviors.change.conditions[0].state",
            "PML-W-CONDITION-STATE-UNPRODUCED",
        ),
    ]


def test_concept_without_transitions_has_no_state_warnings() -> None:
    diagnostics = validate_document(_document(condition="draft")).diagnostics

    assert diagnostics == ()


def test_fully_connected_state_machine_has_no_state_warnings() -> None:
    document = _document({"note": "none -> draft"}, states=["draft", "active", "complete"])
    behaviors = document["domains"]["notes"]["features"]["handling"]["behaviors"]
    behaviors["activate"] = {
        "conditions": [{"concept": "note", "state": "draft"}],
        "trigger": {"statement": "A Member activates a Note."},
        "outcome": {
            "statement": "The Note becomes active.",
            "transitions": {"note": "draft -> active"},
        },
    }
    behaviors["complete"] = {
        "conditions": [{"concept": "note", "state": "active"}],
        "trigger": {"statement": "A Member completes a Note."},
        "outcome": {
            "statement": "The Note becomes complete.",
            "transitions": {"note": "active -> complete"},
        },
    }
    behaviors["remove"] = {
        "trigger": {"statement": "A Member removes a completed Note."},
        "outcome": {
            "statement": "The completed Note ceases to exist.",
            "transitions": {"note": "complete -> none"},
        },
    }

    assert validate_document(document).diagnostics == ()


def test_compiled_transitions_are_canonical_and_indexed_by_concept() -> None:
    document = _document({"note": "none -> draft"})
    document["concepts"]["task"] = {"meaning": "A Task.", "states": ["draft"]}
    document["domains"]["notes"]["features"]["handling"]["behaviors"]["change"]["outcome"]["transitions"] = {  # type: ignore[index]
        "task": "none -> draft",
        "note": "none -> draft",
    }
    resolution = validate_document(document)

    assert resolution.compiled_model is not None
    completion = resolution.compiled_model["behaviors"][0]["outcome"]["case"]
    assert completion["transitions"] == [
        {"concept": "note", "from": "none", "to": "draft"},
        {"concept": "task", "from": "none", "to": "draft"},
    ]
    assert resolution.compiled_model["concepts"][0]["transitions"] == [
        {
            "from": "none",
            "to": "draft",
            "completion": "domains.notes.features.handling.behaviors.change.outcome",
        }
    ]


def test_outcome_alternatives_and_failures_accept_transitions() -> None:
    document = _document()
    behavior = document["domains"]["notes"]["features"]["handling"]["behaviors"]["change"]
    behavior["outcome"] = {
        "one_of": {
            "create": {
                "statement": "The Note enters draft.",
                "transitions": {"note": "none -> draft"},
            },
            "activate": {
                "statement": "The Note becomes active.",
                "transitions": {"note": "draft -> active"},
            },
        }
    }
    behavior["failures"] = {
        "removed": {
            "statement": "The active Note ceases to exist.",
            "transitions": {"note": "active -> none"},
        }
    }

    resolution = validate_document(document)

    assert resolution.diagnostics == ()
    assert resolution.compiled_model is not None
    outcome = resolution.compiled_model["behaviors"][0]["outcome"]
    assert all("transitions" in case for case in outcome["cases"])
    assert "transitions" in resolution.compiled_model["behaviors"][0]["failures"][0]


def test_graph_state_edge_matches_the_golden_snapshot(capsys) -> None:
    source = Path(__file__).parent / "fixtures" / "state-transitions.pml.yaml"
    snapshot = Path(__file__).parent / "fixtures" / "state-transitions.graph.dot"

    assert validate_file(source) == []
    assert main(["graph", str(source)]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.encode("utf-8") == snapshot.read_bytes()
