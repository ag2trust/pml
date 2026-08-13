"""Shared definition reference resolver coverage."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from pml.obligations import (
    enumerate_architecture_obligations,
    enumerate_obligations,
)
from pml.resolver import ReferenceResolver, resolve_references
from pml.validator import load_document, validate_document


ROOT = Path(__file__).resolve().parents[1]
COMPILED_SCHEMA = json.loads(
    (ROOT / "schema" / "pml-compiled-model.schema.json").read_text()
)


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
    assert resolution.compiled_model is not None


def test_resolver_emits_complete_model_for_diagnostic_free_definition() -> None:
    resolution = validate_document(_document("assistant-creation.pml.yaml"))
    model = resolution.compiled_model

    assert resolution.diagnostics == ()
    assert model is not None
    assert list(Draft202012Validator(COMPILED_SCHEMA).iter_errors(model)) == []
    assert set(model) == {
        "format",
        "format_version",
        "language_version",
        "definition_digest",
        "project",
        "vocabulary",
        "actors",
        "concepts",
        "architecture",
        "domains",
        "features",
        "behaviors",
        "use_cases",
        "signals",
        "relationships",
        "use_case_memberships",
        "obligations",
    }
    assert model["signals"][0]["producer"]["completion"].endswith(".outcome")
    assert model["signals"][0]["consumers"][0]["trigger"].endswith(".trigger")
    assert {obligation["kind"] for obligation in model["obligations"]} >= {
        "conditions",
        "trigger",
        "completion",
        "outcome",
        "failure",
        "rule",
        "use_case",
    }


def test_resolver_withholds_model_for_reference_diagnostics() -> None:
    resolution = resolve_references(
        _document("behavior-transition-invalid.pml.yaml")
    )

    assert resolution.diagnostics
    assert resolution.compiled_model is None
    assert resolution.model is None


def test_validated_resolver_withholds_model_for_nonreference_diagnostics() -> None:
    resolution = validate_document(_document("architecture-invalid.pml.yaml"))

    assert resolution.diagnostics
    assert resolution.compiled_model is None


def test_resolver_records_architecture_references_by_canonical_node() -> None:
    resolution = resolve_references(_document("architecture-decisions.pml.yaml"))

    assert resolution.architecture_references == {
        "durable_store": ("domains.records.features.preservation",)
    }
    assert resolution.diagnostics == ()


def test_reference_resolver_enumerates_existing_obligations() -> None:
    document = _document("architecture-decisions.pml.yaml")
    resolver = ReferenceResolver(document)

    assert list(resolver.enumerate_obligations()) == list(
        enumerate_obligations(document)
    )
    assert list(resolver.enumerate_architecture_obligations()) == list(
        enumerate_architecture_obligations(document)
    )


def test_resolver_uses_stable_obligation_ids_for_every_signal_producer() -> None:
    document = _document("behavior-one-of-output.pml.yaml")
    resolution = resolve_references(document)
    behavior = "domains.email.features.triage.behaviors.importance_decision"
    obligation_ids = {item.id for item in enumerate_obligations(document)}

    assert {
        signal_id: signal.completion
        for signal_id, signal in resolution.signals.items()
    } == {
        "important_email_processed": f"{behavior}.outcome.important",
        "ordinary_email_processed": f"{behavior}.outcome.ordinary",
        "email_processing_failed": f"{behavior}.failures.processing_failure",
    }
    assert resolution.signals["important_email_processed"].path == (
        f"{behavior}.outcome.one_of.important.signal"
    )
    assert {
        signal.completion for signal in resolution.signals.values()
    } <= obligation_ids


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
