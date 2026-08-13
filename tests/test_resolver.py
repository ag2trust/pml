"""Shared definition reference resolver coverage."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from pml.obligations import (
    enumerate_architecture_obligations,
    enumerate_obligations,
)
from pml.resolver import (
    ReferenceResolver,
    resolve_definition,
    resolve_references,
)
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
    assert resolution.compiled_model is None


def test_resolver_emits_complete_model_for_diagnostic_free_definition() -> None:
    resolution = resolve_definition(_document("assistant-creation.pml.yaml"))
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


def test_compiled_flattened_records_are_sorted_by_complete_path() -> None:
    behavior = {
        "trigger": {"statement": "A request occurs."},
        "outcome": {"statement": "A visible result occurs."},
    }
    document = {
        "pml": "0.1-draft",
        "project": {
            "id": "ordering",
            "name": "Ordering",
            "purpose": "Exercise compiled path ordering.",
        },
        "actors": {"member": {"meaning": "A participant."}},
        "domains": {
            "a": {
                "purpose": "Normal ancestor.",
                "features": {
                    "f": {
                        "purpose": "Normal feature.",
                        "behaviors": {"b": behavior},
                        "use_cases": {
                            "u": {
                                "actor": "member",
                                "goal": "Observe a normal result.",
                                "behaviors": ["domains.a.features.f.behaviors.b"],
                            }
                        },
                    }
                },
            },
            "a\n": {
                "purpose": "Line-feed ancestor.",
                "features": {
                    "f": {
                        "purpose": "Line-feed feature.",
                        "behaviors": {"b": behavior},
                        "use_cases": {
                            "u": {
                                "actor": "member",
                                "goal": "Observe a line-feed result.",
                                "behaviors": ["domains.a.features.f.behaviors.b"],
                            }
                        },
                    }
                },
            },
        },
    }

    resolution = resolve_definition(document)
    model = resolution.compiled_model

    assert resolution.diagnostics == ()
    assert model is not None
    assert list(Draft202012Validator(COMPILED_SCHEMA).iter_errors(model)) == []
    for collection in ("features", "behaviors", "use_cases"):
        paths = [record["path"] for record in model[collection]]
        assert paths == sorted(paths)
        assert paths[0].startswith("domains.a\n.features")


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


def test_reference_clean_schema_invalid_definition_cannot_compile() -> None:
    document = _document("assistant-creation.pml.yaml")
    document["project"]["unknown"] = "not part of PML"

    references = resolve_references(document)
    resolution = resolve_definition(document)

    assert references.diagnostics == ()
    assert references.compiled_model is None
    assert [(item.path, item.code) for item in resolution.diagnostics] == [
        ("project", "schema")
    ]
    assert resolution.compiled_model is None


def test_reference_clean_incomplete_definition_returns_diagnostics_not_model() -> None:
    document = _document("assistant-creation.pml.yaml")
    del document["domains"]["assistants"]["features"]["creation"]["behaviors"][
        "created_assistant_visibility"
    ]["outcome"]

    references = resolve_references(document)
    resolution = resolve_definition(document)

    assert references.diagnostics == ()
    assert references.compiled_model is None
    assert any(item.code == "schema" for item in resolution.diagnostics)
    assert resolution.compiled_model is None


def test_reference_clean_local_language_invalid_definition_cannot_compile() -> None:
    document = _document("assistant-creation.pml.yaml")
    behavior = document["domains"]["assistants"]["features"]["creation"][
        "behaviors"
    ]["assistant_creation"]
    behavior["trigger"]["statement"] = "The REST API receives a request."

    references = ReferenceResolver(document).resolve()
    resolution = resolve_definition(document)

    assert references.diagnostics == ()
    assert references.compiled_model is None
    assert [(item.path, item.code) for item in resolution.diagnostics] == [
        (
            "domains.assistants.features.creation.behaviors."
            "assistant_creation.trigger.statement",
            "implementation-detail",
        )
    ]
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


def test_compiled_model_preserves_resolved_transition_obligations() -> None:
    document = _document("behavior-one-of-output.pml.yaml")
    behavior = "domains.email.features.triage.behaviors.importance_decision"
    resolver = ReferenceResolver(document)
    resolution = resolve_definition(document)
    model = resolution.compiled_model

    expected_ids = [
        f"{behavior}.conditions",
        f"{behavior}.trigger.received",
        f"{behavior}.trigger.requested_again",
        f"{behavior}.completion",
        f"{behavior}.outcome",
        f"{behavior}.outcome.important",
        f"{behavior}.outcome.ordinary",
        f"{behavior}.failures.processing_failure",
    ]

    assert resolution.diagnostics == ()
    assert model is not None
    assert [
        obligation.id for obligation in resolver.enumerate_obligations(behavior)
    ] == expected_ids
    assert [
        obligation["id"]
        for obligation in model["obligations"]
        if obligation["node"] == behavior
    ] == sorted(expected_ids)
    assert model["behaviors"] == [
        {
            "id": "importance_decision",
            "path": behavior,
            "feature": "domains.email.features.triage",
            "conditions": {
                "statements": ["The inbound email has content and a sender."],
                "obligation": f"{behavior}.conditions",
            },
            "trigger": {
                "kind": "one_of",
                "cases": [
                    {
                        "id": "received",
                        "obligation": f"{behavior}.trigger.received",
                        "statement": "The product receives an inbound email for triage.",
                    },
                    {
                        "id": "requested_again",
                        "obligation": f"{behavior}.trigger.requested_again",
                        "statement": "A Member requests another importance decision for the inbound email.",
                    },
                ],
            },
            "completion_obligation": f"{behavior}.completion",
            "outcome": {
                "kind": "one_of",
                "exclusivity_obligation": f"{behavior}.outcome",
                "cases": [
                    {
                        "id": "important",
                        "obligation": f"{behavior}.outcome.important",
                        "statement": "The inbound email is classified as important.",
                        "signal": "important_email_processed",
                    },
                    {
                        "id": "ordinary",
                        "obligation": f"{behavior}.outcome.ordinary",
                        "statement": "The inbound email is classified as ordinary.",
                        "signal": "ordinary_email_processed",
                    },
                ],
            },
            "failures": [
                {
                    "id": "processing_failure",
                    "obligation": f"{behavior}.failures.processing_failure",
                    "statement": "A visible failure indicates that a complete importance decision could not be supported.",
                    "signal": "email_processing_failed",
                }
            ],
            "rule_obligations": [],
            "related_to": [],
            "use_cases": [],
        }
    ]


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
