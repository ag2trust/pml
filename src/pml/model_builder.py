"""Materialization of the approved compiled semantic model from resolver output."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, TYPE_CHECKING, cast

from pml.compiled_model import CompiledModel, CompiledObligation

if TYPE_CHECKING:
    from pml.resolver import Obligation, ReferenceResolver, ResolvedDefinition


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _sequence(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _definition_digest(document: Mapping[str, Any]) -> str:
    """Return the approved compact canonical digest of one valid definition."""

    encoded = json.dumps(
        dict(document), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _rule_obligations(node_path: str, definition: Mapping[str, Any]) -> list[str]:
    return sorted(
        f"{node_path}.rules.{rule_id}"
        for rule_id in _mapping(definition.get("rules"))
    )


def _signal_reference(definition: Mapping[str, Any]) -> str | None:
    signal = definition.get("signal")
    if isinstance(signal, dict):
        signal_id = signal.get("id")
        return signal_id if isinstance(signal_id, str) else None
    return signal if isinstance(signal, str) else None


def _compiled_completion_definition(definition: Mapping[str, Any]) -> dict[str, Any]:
    compiled = {"statement": definition["statement"]}
    signal_id = _signal_reference(definition)
    if signal_id is not None:
        compiled["signal"] = signal_id
    return compiled


def _compiled_trigger(behavior_path: str, definition: Mapping[str, Any]) -> dict[str, Any]:
    alternatives = definition.get("one_of")
    if isinstance(alternatives, dict):
        cases = []
        for alternative_id in sorted(alternatives):
            case_definition = alternatives[alternative_id]
            case = {
                "id": alternative_id,
                "obligation": f"{behavior_path}.trigger.{alternative_id}",
            }
            if "statement" in case_definition:
                case["statement"] = case_definition["statement"]
            else:
                case["signal"] = case_definition["signal"]
            cases.append(case)
        return {"kind": "one_of", "cases": cases}

    case = {"obligation": f"{behavior_path}.trigger"}
    if "statement" in definition:
        case["statement"] = definition["statement"]
    else:
        case["signal"] = definition["signal"]
    return {"kind": "direct", "case": case}


def _compiled_outcome(behavior_path: str, definition: Mapping[str, Any]) -> dict[str, Any]:
    alternatives = definition.get("one_of")
    if isinstance(alternatives, dict):
        cases = []
        for alternative_id in sorted(alternatives):
            case = {
                "id": alternative_id,
                "obligation": f"{behavior_path}.outcome.{alternative_id}",
                **_compiled_completion_definition(alternatives[alternative_id]),
            }
            cases.append(case)
        return {
            "kind": "one_of",
            "exclusivity_obligation": f"{behavior_path}.outcome",
            "cases": cases,
        }

    return {
        "kind": "direct",
        "case": {
            "obligation": f"{behavior_path}.outcome",
            **_compiled_completion_definition(definition),
        },
    }


def _compiled_experience(definition: Mapping[str, Any]) -> dict[str, Any]:
    surfaces = []
    for surface_id, surface in sorted(
        _mapping(definition.get("surfaces")).items()
    ):
        states = [
            {"id": state_id, "statements": list(statements)}
            for state_id, statements in sorted(
                _mapping(surface.get("states")).items()
            )
        ]
        surfaces.append(
            {
                "id": surface_id,
                "contains": _sequence(surface.get("contains")),
                "states": states,
                "accessibility": _sequence(surface.get("accessibility")),
                "responsive_behavior": _sequence(
                    surface.get("responsive_behavior")
                ),
            }
        )
    return {"surfaces": surfaces}


def _compiled_obligation(obligation: Obligation) -> CompiledObligation:
    definition = obligation.definition
    if obligation.section == "conditions":
        kind = "conditions"
        compiled_definition = {"statements": list(definition["all"])}
    elif obligation.section == "trigger":
        kind = "trigger"
        compiled_definition = (
            {"statement": definition["statement"]}
            if "statement" in definition
            else {"signal": definition["signal"]}
        )
    elif obligation.section == "completion":
        kind = "completion"
        compiled_definition = {
            "outcomes": sorted(
                f"{obligation.node_id}.outcome"
                + ("" if outcome_id == "outcome" else f".{outcome_id}")
                for outcome_id in definition["outcomes"]
            ),
            "failures": sorted(
                f"{obligation.node_id}.failures.{failure_id}"
                for failure_id in definition["failures"]
            ),
        }
    elif obligation.section == "outcome" and "one_of" in definition:
        kind = "outcome_exclusivity"
        compiled_definition = {
            "alternatives": sorted(
                f"{obligation.node_id}.outcome.{alternative_id}"
                for alternative_id in definition["one_of"]
            )
        }
    elif obligation.section == "outcome":
        kind = "outcome"
        compiled_definition = _compiled_completion_definition(definition)
    elif obligation.section == "failures":
        kind = "failure"
        compiled_definition = _compiled_completion_definition(definition)
    elif obligation.section == "rules":
        kind = "rule"
        compiled_definition = {"statement": definition["statement"]}
    elif obligation.section == "use_cases":
        kind = "use_case"
        compiled_definition = {
            "actor": definition["actor"],
            "goal": definition["goal"],
            "behaviors": list(definition["behaviors"]),
        }
    else:
        kind = "architecture_constraint"
        compiled_definition = {"statement": definition["statement"]}

    return cast(
        CompiledObligation,
        {
            "id": obligation.id,
            "node": obligation.node_id,
            "kind": kind,
            "definition": compiled_definition,
        },
    )


def _signal_consumers(
    resolution: ResolvedDefinition,
) -> dict[str, list[dict[str, str]]]:
    consumers: dict[str, list[dict[str, str]]] = {
        signal_id: [] for signal_id in resolution.signals
    }
    for behavior_path, behavior in resolution.behaviors.items():
        trigger = _mapping(behavior.get("trigger"))
        alternatives = trigger.get("one_of")
        if isinstance(alternatives, dict):
            cases = (
                (case_id, case_definition)
                for case_id, case_definition in alternatives.items()
            )
        else:
            cases = ((None, trigger),)
        for case_id, case_definition in cases:
            signal_id = case_definition.get("signal")
            if not isinstance(signal_id, str):
                continue
            trigger_path = f"{behavior_path}.trigger"
            if case_id is not None:
                trigger_path += f".{case_id}"
            consumers[signal_id].append(
                {"behavior": behavior_path, "trigger": trigger_path}
            )
    for entries in consumers.values():
        entries.sort(key=lambda item: (item["behavior"], item["trigger"]))
    return consumers


def _relationships(
    resolution: ResolvedDefinition,
) -> list[dict[str, Any]]:
    declarations: dict[tuple[str, str], set[str]] = {}
    for node_path, node in resolution.nodes.items():
        for target in _sequence(node.get("related_to")):
            endpoints = tuple(sorted((node_path, target)))
            declarations.setdefault(endpoints, set()).add(node_path)
    return [
        {
            "kind": "related_to",
            "endpoints": endpoints,
            "declared_by": sorted(declarations[endpoints]),
        }
        for endpoints in sorted(declarations)
    ]


def _build_compiled_model(
    document: Mapping[str, Any],
    resolver: ReferenceResolver,
    resolution: ResolvedDefinition,
) -> CompiledModel:
    """Build the complete v1 model from one diagnostic-free resolver result."""

    if resolution.diagnostics:
        raise ValueError("cannot compile a definition with diagnostics")

    domains_definition = _mapping(document.get("domains"))
    project_definition = _mapping(document.get("project"))

    memberships = sorted(
        (
            {"use_case": use_case_path, "behavior": behavior_path}
            for use_case_path, use_case in resolution.use_cases.items()
            for behavior_path in _sequence(use_case.get("behaviors"))
        ),
        key=lambda item: (item["use_case"], item["behavior"]),
    )
    behavior_use_cases: dict[str, list[str]] = {
        behavior_path: [] for behavior_path in resolution.behaviors
    }
    for membership in memberships:
        behavior_use_cases[membership["behavior"]].append(membership["use_case"])

    domains = []
    features = []
    behaviors = []
    use_cases = []
    for domain_id, domain in sorted(domains_definition.items()):
        domain_path = f"domains.{domain_id}"
        feature_definitions = _mapping(domain.get("features"))
        domains.append(
            {
                "id": domain_id,
                "path": domain_path,
                "purpose": domain["purpose"],
                "rule_obligations": _rule_obligations(domain_path, domain),
                "features": sorted(
                    f"{domain_path}.features.{feature_id}"
                    for feature_id in feature_definitions
                ),
            }
        )
        for feature_id, feature in sorted(feature_definitions.items()):
            feature_path = f"{domain_path}.features.{feature_id}"
            behavior_definitions = _mapping(feature.get("behaviors"))
            use_case_definitions = _mapping(feature.get("use_cases"))
            compiled_feature = {
                "id": feature_id,
                "path": feature_path,
                "domain": domain_path,
                "purpose": feature["purpose"],
                "actors": _sequence(feature.get("actors")),
                "rule_obligations": _rule_obligations(feature_path, feature),
                "use_cases": sorted(
                    f"{feature_path}.use_cases.{use_case_id}"
                    for use_case_id in use_case_definitions
                ),
                "behaviors": sorted(
                    f"{feature_path}.behaviors.{behavior_id}"
                    for behavior_id in behavior_definitions
                ),
                "related_to": _sequence(feature.get("related_to")),
                "architecture": [
                    f"architecture.{decision_id}"
                    for decision_id in _sequence(feature.get("architecture"))
                ],
            }
            experience = feature.get("experience")
            if isinstance(experience, dict):
                compiled_feature["experience"] = _compiled_experience(experience)
            features.append(compiled_feature)

            for behavior_id, behavior in sorted(behavior_definitions.items()):
                behavior_path = f"{feature_path}.behaviors.{behavior_id}"
                failure_definitions = _mapping(behavior.get("failures"))
                compiled_behavior = {
                    "id": behavior_id,
                    "path": behavior_path,
                    "feature": feature_path,
                    "trigger": _compiled_trigger(
                        behavior_path, _mapping(behavior.get("trigger"))
                    ),
                    "completion_obligation": f"{behavior_path}.completion",
                    "outcome": _compiled_outcome(
                        behavior_path, _mapping(behavior.get("outcome"))
                    ),
                    "failures": [
                        {
                            "id": failure_id,
                            "obligation": f"{behavior_path}.failures.{failure_id}",
                            **_compiled_completion_definition(failure),
                        }
                        for failure_id, failure in sorted(failure_definitions.items())
                    ],
                    "rule_obligations": _rule_obligations(behavior_path, behavior),
                    "related_to": _sequence(behavior.get("related_to")),
                    "use_cases": sorted(behavior_use_cases[behavior_path]),
                }
                conditions = behavior.get("conditions")
                if isinstance(conditions, list):
                    compiled_behavior["conditions"] = {
                        "statements": list(conditions),
                        "obligation": f"{behavior_path}.conditions",
                    }
                behaviors.append(compiled_behavior)

            for use_case_id, use_case in sorted(use_case_definitions.items()):
                use_case_path = f"{feature_path}.use_cases.{use_case_id}"
                use_cases.append(
                    {
                        "id": use_case_id,
                        "path": use_case_path,
                        "feature": feature_path,
                        "actor": use_case["actor"],
                        "goal": use_case["goal"],
                        "behaviors": list(use_case["behaviors"]),
                        "obligation": use_case_path,
                    }
                )

    # These collections flatten records from multiple hierarchy levels. Sorting
    # source keys at each level is not equivalent to sorting the completed path
    # when an accepted ID has a terminal line feed, because LF sorts before the
    # path separator. The compiled v1 contract orders the flattened records by
    # their complete canonical path.
    features.sort(key=lambda feature: feature["path"])
    behaviors.sort(key=lambda behavior: behavior["path"])
    use_cases.sort(key=lambda use_case: use_case["path"])

    signal_consumers = _signal_consumers(resolution)
    signals = []
    for signal_id, signal in sorted(resolution.signals.items()):
        compiled_signal = {
            "id": signal_id,
            "meaning": signal.definition["meaning"],
            "producer": {
                "behavior": signal.behavior,
                "completion": signal.completion,
            },
            "consumers": signal_consumers[signal_id],
        }
        subject = signal.definition.get("subject")
        if isinstance(subject, str):
            compiled_signal["subject"] = subject
        signals.append(compiled_signal)

    product_obligations = list(resolver.enumerate_obligations())
    architecture_obligations = list(resolver.enumerate_architecture_obligations())
    obligations = sorted(
        (
            _compiled_obligation(obligation)
            for obligation in product_obligations + architecture_obligations
        ),
        key=lambda obligation: obligation["id"],
    )

    model = {
        "format": "pml.compiled",
        "format_version": 1,
        "language_version": "0.1-draft",
        "definition_digest": _definition_digest(document),
        "project": {
            "id": project_definition["id"],
            "name": project_definition["name"],
            "purpose": project_definition["purpose"],
            "rule_obligations": _rule_obligations("project", document),
            "domains": [domain["path"] for domain in domains],
        },
        "vocabulary": [
            {
                "term": term,
                "meaning": definition["meaning"],
                "forbidden_synonyms": _sequence(
                    definition.get("forbidden_synonyms")
                ),
            }
            for term, definition in sorted(
                _mapping(document.get("vocabulary")).items()
            )
        ],
        "actors": [
            {"id": actor_id, "meaning": definition["meaning"]}
            for actor_id, definition in sorted(resolution.actors.items())
        ],
        "concepts": [
            {
                "id": concept_id,
                "meaning": definition["meaning"],
                "states": _sequence(definition.get("states")),
            }
            for concept_id, definition in sorted(resolution.concepts.items())
        ],
        "architecture": [
            {
                "id": decision_id,
                "path": f"architecture.{decision_id}",
                "category": decision["category"],
                "selection": decision["selection"],
                "rationale": decision["rationale"],
                "constraint_obligations": sorted(
                    f"architecture.{decision_id}.constraints.{constraint_id}"
                    for constraint_id in _mapping(decision.get("constraints"))
                ),
                "referenced_by": sorted(
                    resolution.architecture_references[decision_id]
                ),
            }
            for decision_id, decision in sorted(resolution.architecture.items())
        ],
        "domains": domains,
        "features": features,
        "behaviors": behaviors,
        "use_cases": use_cases,
        "signals": signals,
        "relationships": _relationships(resolution),
        "use_case_memberships": memberships,
        "obligations": obligations,
    }
    return cast(CompiledModel, model)
