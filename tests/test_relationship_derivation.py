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


def test_high_concept_collision_keeps_one_source_per_feature_pair() -> None:
    """Compile the schema bounds without retaining every concept provenance tag."""

    concept_ids = [f"concept_{index}" for index in range(25)]
    features: dict[str, dict[str, Any]] = {}
    for feature_index in range(625):
        behaviors = {}
        for behavior_index, start in enumerate(range(0, len(concept_ids), 7)):
            behaviors[f"observe_{behavior_index}"] = {
                "conditions": [
                    {"concept": concept_id, "state": "ready"}
                    for concept_id in concept_ids[start : start + 7]
                ],
                "trigger": {"statement": "A Member observes a Concept."},
                "outcome": {"statement": "The Concept remains observable."},
            }
        feature = {"purpose": "Observe concepts.", "behaviors": behaviors}
        if feature_index == 0:
            feature["related_to"] = ["domains.domain_0.features.feature_1"]
        features[f"feature_{feature_index}"] = feature

    document = {
        "pml": "0.1-draft",
        "project": {
            "id": "collision",
            "name": "Collision",
            "purpose": "Compile maximum concept collisions.",
        },
        "concepts": {
            concept_id: {"meaning": "A Concept.", "states": ["ready"]}
            for concept_id in concept_ids
        },
        "domains": {
            f"domain_{domain_index}": {
                "purpose": "Contain features.",
                "features": {
                    feature_id: features[feature_id]
                    for feature_id in list(features)[
                        domain_index * 25 : (domain_index + 1) * 25
                    ]
                },
            }
            for domain_index in range(25)
        },
    }

    resolution = validate_document(document)

    assert resolution.diagnostics == ()
    assert resolution.compiled_model is not None
    relationships = resolution.compiled_model["relationships"]
    assert len(relationships) == 625 * 624 // 2
    authored_relationship_found = False
    for relationship in relationships:
        if relationship["endpoints"] == [
            "domains.domain_0.features.feature_0",
            "domains.domain_0.features.feature_1",
        ]:
            authored_relationship_found = True
            assert relationship["declared_by"] == [
                "domains.domain_0.features.feature_0"
            ]
            assert relationship["source"] == "authored"
        else:
            assert relationship["source"] == "concept:concept_0"
    assert authored_relationship_found
