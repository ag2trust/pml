from pathlib import Path

import pytest
import yaml

from pml.validator import validate_file


ROOT = Path(__file__).resolve().parents[1]


def _manifest(tmp_path: Path, behavior: dict, *, use_case: dict | None = None) -> Path:
    feature: dict[str, object] = {
        "purpose": "Handle Notes.",
        "behaviors": {"note_handling": behavior},
    }
    if use_case is not None:
        feature["use_cases"] = {"handle_note": use_case}
    document = {
        "pml": "0.1-draft",
        "project": {
            "id": "sample",
            "name": "Sample",
            "purpose": "Demonstrate transition validation.",
        },
        "actors": {"member": {"meaning": "An authorized participant."}},
        "concepts": {"note": {"meaning": "A recorded Note."}},
        "domains": {
            "notes": {
                "purpose": "Manage Notes.",
                "features": {"handling": feature},
            }
        },
    }
    path = tmp_path / "transition.pml.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "example",
    [
        "behavior-direct-output.pml.yaml",
        "behavior-one-of-output.pml.yaml",
    ],
)
def test_transition_examples_are_valid(example: str) -> None:
    assert validate_file(ROOT / "examples" / example) == []


def test_complete_transition_shape_is_valid(tmp_path: Path) -> None:
    behavior = {
        "conditions": ["The Note needs handling."],
        "trigger": {
            "one_of": {
                "member_request": {"statement": "A Member requests handling."},
                "prior_signal": {"signal": "note_ready"},
            }
        },
        "outcome": {
            "one_of": {
                "handled": {"statement": "The Note is handled."},
                "archived": {"statement": "The Note is archived."},
            }
        },
        "failures": {
            "rejected": {"statement": "The request is visibly rejected."}
        },
    }
    producer = {
        "trigger": {"statement": "A Note becomes ready."},
        "outcome": {
            "statement": "The Note is ready for handling.",
            "signal": {
                "id": "note_ready",
                "subject": "note",
                "meaning": "A Note is ready for handling.",
            },
        },
    }
    path = _manifest(tmp_path, behavior)
    document = yaml.safe_load(path.read_text())
    document["domains"]["notes"]["features"]["handling"]["behaviors"][
        "note_readiness"
    ] = producer
    path.write_text(yaml.safe_dump(document, sort_keys=False))

    assert validate_file(path) == []


@pytest.mark.parametrize(
    "legacy_key",
    ["context", "output", "reactions", "architecture", "emits", "purpose"],
)
def test_removed_behavior_keys_are_rejected(tmp_path: Path, legacy_key: str) -> None:
    behavior = {
        "trigger": {"statement": "A Member requests handling."},
        "outcome": {"statement": "The Note is handled."},
        legacy_key: [] if legacy_key != "purpose" else "Legacy intent.",
    }

    diagnostics = validate_file(_manifest(tmp_path, behavior))

    assert any(item.code == "schema" and legacy_key in item.message for item in diagnostics)


@pytest.mark.parametrize("field", ["trigger", "outcome"])
def test_transition_requires_trigger_and_outcome(tmp_path: Path, field: str) -> None:
    behavior = {
        "trigger": {"statement": "A Member requests handling."},
        "outcome": {"statement": "The Note is handled."},
    }
    del behavior[field]

    diagnostics = validate_file(_manifest(tmp_path, behavior))

    assert any(
        item.code == "schema" and f"'{field}' is a required property" in item.message
        for item in diagnostics
    )


@pytest.mark.parametrize("field", ["trigger", "outcome"])
def test_direct_and_one_of_forms_are_exclusive(tmp_path: Path, field: str) -> None:
    behavior = {
        "trigger": {"statement": "A Member requests handling."},
        "outcome": {"statement": "The Note is handled."},
    }
    behavior[field] = {
        "statement": "A direct transition statement.",
        "one_of": {
            "first": {"statement": "The first alternative occurs."},
            "second": {"statement": "The second alternative occurs."},
        },
    }

    diagnostics = validate_file(_manifest(tmp_path, behavior))

    assert any(item.code == "schema" and item.path.endswith(f".{field}") for item in diagnostics)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("conditions", [f"Condition {index}." for index in range(8)]),
        (
            "trigger",
            {
                "one_of": {
                    f"case_{index}": {"statement": f"Trigger {index}."}
                    for index in range(8)
                }
            },
        ),
        (
            "outcome",
            {
                "one_of": {
                    f"case_{index}": {"statement": f"Outcome {index}."}
                    for index in range(8)
                }
            },
        ),
        (
            "failures",
            {
                f"failure_{index}": {"statement": f"Failure {index}."}
                for index in range(8)
            },
        ),
    ],
)
def test_transition_collections_are_bounded(
    tmp_path: Path, field: str, value: object
) -> None:
    behavior = {
        "trigger": {"statement": "A Member requests handling."},
        "outcome": {"statement": "The Note is handled."},
        field: value,
    }

    diagnostics = validate_file(_manifest(tmp_path, behavior))

    assert any(item.code == "schema" and f".{field}" in item.path for item in diagnostics)


def test_signal_and_use_case_reference_diagnostics() -> None:
    diagnostics = validate_file(
        ROOT / "examples" / "behavior-transition-invalid.pml.yaml"
    )

    assert {item.code for item in diagnostics} == {
        "duplicate-signal",
        "undefined-reference",
    }
    assert {item.path for item in diagnostics} == {
        "domains.messaging.features.handling.behaviors.message_handling.outcome.signal.subject",
        "domains.messaging.features.handling.behaviors.duplicate_producer.trigger.signal",
        "domains.messaging.features.handling.behaviors.duplicate_producer.outcome.signal.id",
        "domains.messaging.features.handling.use_cases.handle_message.behaviors",
    }


def test_transition_text_is_normative_without_must_and_rejects_implementation_detail(
    tmp_path: Path,
) -> None:
    behavior = {
        "conditions": ["The Note is properly stored in notes.py."],
        "trigger": {"statement": "The REST API receives a request."},
        "outcome": {"statement": "The save_note() function returns the Note."},
        "failures": {
            "failed": {"statement": "The framework properly reports failure."}
        },
    }

    diagnostics = validate_file(_manifest(tmp_path, behavior))

    assert "non-normative" not in {item.code for item in diagnostics}
    assert {item.code for item in diagnostics} == {
        "ambiguous-language",
        "implementation-detail",
    }
