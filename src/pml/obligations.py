"""Enumeration of semantic nodes and their approved obligations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator


OBLIGATION_SECTIONS = ("rules", "use_cases", "reactions")


@dataclass(frozen=True)
class Obligation:
    id: str
    node_id: str
    section: str
    local_id: str
    definition: dict[str, Any]


def verification_coverage(plan: dict[str, Any]) -> dict[str, float]:
    """Return approved coverage by evidence method."""

    return {
        "deterministic_probe": sum(plan.get("probes", {}).values()),
        "agent_judgment": float(plan.get("agent_judgment", 0)),
        "human_attestation": float(plan.get("human_attestation", 0)),
    }


def required_methods(plan: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        method for method, coverage in verification_coverage(plan).items() if coverage
    )


def verification_plan(
    bindings: dict[str, Any], obligation: Obligation
) -> dict[str, Any]:
    if obligation.node_id.startswith("architecture."):
        decision_id = obligation.node_id.removeprefix("architecture.")
        return (
            bindings.get("architecture", {})
            .get(decision_id, {})
            .get("verification", {})
            .get(obligation.id, {})
        )
    return (
        bindings.get("bindings", {})
        .get(obligation.node_id, {})
        .get("verification", {})
        .get(obligation.id, {})
    )

def iter_nodes(document: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield every state-bearing rule scope, feature, and direct behavior."""

    if document.get("rules"):
        yield "project", {"rules": document["rules"]}
    for domain_id, domain in document.get("domains", {}).items():
        if domain.get("rules"):
            yield f"domains.{domain_id}", {"rules": domain["rules"]}
        for feature_id, feature in domain.get("features", {}).items():
            semantic_id = f"domains.{domain_id}.features.{feature_id}"
            yield semantic_id, feature
            behaviors = feature.get("behaviors", {})
            if not isinstance(behaviors, dict):
                continue
            for behavior_id, behavior in behaviors.items():
                if isinstance(behavior, dict):
                    yield f"{semantic_id}.behaviors.{behavior_id}", behavior


def enumerate_obligations(
    document: dict[str, Any], node_id: str | None = None
) -> Iterator[Obligation]:
    for semantic_id, node in iter_nodes(document):
        if node_id is not None and semantic_id != node_id:
            continue
        output = node.get("output")
        if isinstance(output, dict):
            alternatives = output.get("one_of")
            if isinstance(alternatives, dict):
                yield Obligation(
                    id=f"{semantic_id}.output",
                    node_id=semantic_id,
                    section="output",
                    local_id="output",
                    definition={"one_of": list(alternatives)},
                )
                for alternative_id, definition in alternatives.items():
                    yield Obligation(
                        id=f"{semantic_id}.output.{alternative_id}",
                        node_id=semantic_id,
                        section="output",
                        local_id=alternative_id,
                        definition=definition,
                    )
            else:
                yield Obligation(
                    id=f"{semantic_id}.output",
                    node_id=semantic_id,
                    section="output",
                    local_id="output",
                    definition=output,
                )
        for section in OBLIGATION_SECTIONS:
            for local_id, definition in node.get(section, {}).items():
                yield Obligation(
                    id=f"{semantic_id}.{section}.{local_id}",
                    node_id=semantic_id,
                    section=section,
                    local_id=local_id,
                    definition=definition,
                )


def iter_architecture(document: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield independent, flat architecture decision scopes."""

    for decision_id, decision in document.get("architecture", {}).items():
        yield f"architecture.{decision_id}", decision


def enumerate_architecture_obligations(
    document: dict[str, Any], node_id: str | None = None
) -> Iterator[Obligation]:
    """Resolve architecture constraints without mixing them into product obligations."""

    for semantic_id, decision in iter_architecture(document):
        if node_id is not None and semantic_id != node_id:
            continue
        for local_id, definition in decision.get("constraints", {}).items():
            yield Obligation(
                id=f"{semantic_id}.constraints.{local_id}",
                node_id=semantic_id,
                section="constraints",
                local_id=local_id,
                definition=definition,
            )
