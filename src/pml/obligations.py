"""Enumeration of semantic nodes and their approved obligations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator


OBLIGATION_SECTIONS = ("rules", "use_cases", "security", "reactions", "acceptance")


@dataclass(frozen=True)
class Obligation:
    id: str
    node_id: str
    section: str
    local_id: str
    definition: dict[str, Any]

    @property
    def required_methods(self) -> tuple[str, ...]:
        verification = self.definition.get("verification", {})
        return tuple(verification.get("requires", ()))


def iter_nodes(document: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield every feature and recursively nested component by semantic ID."""

    def components(parent_id: str, node: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
        for component_id, component in node.get("components", {}).items():
            semantic_id = f"{parent_id}.components.{component_id}"
            yield semantic_id, component
            yield from components(semantic_id, component)

    for domain_id, domain in document.get("domains", {}).items():
        for feature_id, feature in domain.get("features", {}).items():
            semantic_id = f"domains.{domain_id}.features.{feature_id}"
            yield semantic_id, feature
            yield from components(semantic_id, feature)


def enumerate_obligations(
    document: dict[str, Any], node_id: str | None = None
) -> Iterator[Obligation]:
    for semantic_id, node in iter_nodes(document):
        if node_id is not None and semantic_id != node_id:
            continue
        for section in OBLIGATION_SECTIONS:
            for local_id, definition in node.get(section, {}).items():
                yield Obligation(
                    id=f"{semantic_id}.{section}.{local_id}",
                    node_id=semantic_id,
                    section=section,
                    local_id=local_id,
                    definition=definition,
                )
