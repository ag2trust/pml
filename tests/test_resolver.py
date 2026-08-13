"""Shared definition reference resolver coverage."""

from pathlib import Path

from pml.resolver import resolve_references
from pml.validator import load_document


ROOT = Path(__file__).resolve().parents[1]


def _document(example: str) -> dict:
    document, diagnostics = load_document(ROOT / "examples" / example)
    assert diagnostics == []
    assert document is not None
    return document


def test_resolver_indexes_definition_identities_and_resolved_signals() -> None:
    resolution = resolve_references(_document("assistant-creation.pml.yaml"))
    feature = "domains.assistants.features.creation"
    producer = f"{feature}.behaviors.assistant_creation"
    consumer = f"{feature}.behaviors.created_assistant_visibility"
    use_case = f"{feature}.use_cases.create_from_scratch"

    assert set(resolution.actors) == {"member"}
    assert set(resolution.concepts) == {"assistant"}
    assert set(resolution.behaviors) == {producer, consumer}
    assert set(resolution.use_cases) == {use_case}
    assert resolution.signals["assistant_created"].behavior == producer
    assert resolution.signals["assistant_created"].completion == f"{producer}.outcome"
    assert resolution.diagnostics == ()


def test_resolver_records_architecture_references_by_canonical_node() -> None:
    resolution = resolve_references(_document("architecture-decisions.pml.yaml"))

    assert resolution.architecture_references == {
        "durable_store": ("domains.records.features.preservation",)
    }
    assert resolution.diagnostics == ()


def test_resolver_preserves_established_reference_diagnostics() -> None:
    resolution = resolve_references(
        _document("behavior-transition-invalid.pml.yaml")
    )

    assert [(item.path, item.code, item.message) for item in resolution.diagnostics] == [
        (
            "domains.messaging.features.handling.behaviors.message_handling.outcome.signal.subject",
            "undefined-reference",
            "unknown concept 'missing_concept'",
        ),
        (
            "domains.messaging.features.handling.behaviors.duplicate_producer.outcome.signal.id",
            "duplicate-signal",
            "signal 'message_handled' is already defined at "
            "domains.messaging.features.handling.behaviors.message_handling.outcome.signal",
        ),
        (
            "domains.messaging.features.handling.use_cases.handle_message.behaviors",
            "undefined-reference",
            "unknown behavior "
            "'domains.messaging.features.handling.behaviors.missing_behavior'",
        ),
        (
            "domains.messaging.features.handling.behaviors.duplicate_producer.trigger.signal",
            "undefined-reference",
            "unknown signal 'missing_signal'",
        ),
    ]
