"""Conformance coverage for compiled relationship derivation."""

from __future__ import annotations

from typing import Any

from pml.model_builder import derive_relationships
from pml.validator import validate_document


def _transition_document(*, related_to: bool = False) -> dict[str, Any]:
    first_feature: dict[str, Any] = {
        "purpose": "Create a note.",
        "behaviors": {
            "create": {
                "trigger": {"statement": "A Member creates a Note."},
                "outcome": {
                    "statement": "The Note enters draft.",
                    "transitions": {"note": "none -> draft"},
                },
            }
        },
    }
    if related_to:
        first_feature["related_to"] = ["domains.notes.features.publish"]
    return {
        "pml": "0.1-draft",
        "project": {
            "id": "relationships",
            "name": "Relationships",
            "purpose": "Derive feature relationships.",
        },
        "concepts": {"note": {"meaning": "A Note.", "states": ["draft", "published"]}},
        "domains": {
            "notes": {
                "purpose": "Manage Notes.",
                "features": {
                    "create": first_feature,
                    "publish": {
                        "purpose": "Publish a note.",
                        "behaviors": {
                            "publish": {
                                "trigger": {"statement": "A Member publishes a Note."},
                                "outcome": {
                                    "statement": "The Note becomes published.",
                                    "transitions": {"note": "draft -> published"},
                                },
                            }
                        },
                    },
                },
            }
        },
    }


def _compiled_relationships(document: dict[str, Any]) -> list[dict[str, Any]]:
    resolution = validate_document(document)

    assert resolution.compiled_model is not None
    assert derive_relationships(resolution) == resolution.compiled_model["relationships"]
    return resolution.compiled_model["relationships"]


def test_shared_transition_concept_derives_feature_relationship() -> None:
    assert _compiled_relationships(_transition_document()) == [
        {
            "kind": "related_to",
            "endpoints": [
                "domains.notes.features.create",
                "domains.notes.features.publish",
            ],
            "declared_by": [],
            "source": "concept:note",
        }
    ]


def test_signal_producer_and_consumer_features_derive_relationship() -> None:
    document = {
        "pml": "0.1-draft",
        "project": {
            "id": "signals",
            "name": "Signals",
            "purpose": "Derive signal relationships.",
        },
        "domains": {
            "notes": {
                "purpose": "Manage Notes.",
                "features": {
                    "create": {
                        "purpose": "Create a note.",
                        "behaviors": {
                            "create": {
                                "trigger": {"statement": "A Member creates a Note."},
                                "outcome": {
                                    "statement": "The Note is created.",
                                    "signal": {
                                        "id": "note_created",
                                        "meaning": "A Note was created.",
                                    },
                                },
                            }
                        },
                    },
                    "notify": {
                        "purpose": "Notify a member.",
                        "behaviors": {
                            "notify": {
                                "trigger": {"signal": "note_created"},
                                "outcome": {
                                    "statement": "The Member is notified."
                                },
                            }
                        },
                    },
                },
            }
        },
    }

    assert _compiled_relationships(document) == [
        {
            "kind": "related_to",
            "endpoints": [
                "domains.notes.features.create",
                "domains.notes.features.notify",
            ],
            "declared_by": [],
            "source": "signal:note_created",
        }
    ]


def test_authored_relationship_takes_precedence_over_concept_derivation() -> None:
    assert _compiled_relationships(_transition_document(related_to=True)) == [
        {
            "kind": "related_to",
            "endpoints": [
                "domains.notes.features.create",
                "domains.notes.features.publish",
            ],
            "declared_by": ["domains.notes.features.create"],
            "source": "authored",
        }
    ]
