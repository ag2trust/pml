"""Deterministic DOT projection of the explicit compiled PML graph."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pml.explain import (
    CompiledModelIndexes,
    build_compiled_model_indexes,
    is_supported_model,
)


GraphMeaning = Literal[
    "causal",
    "related_to",
    "derived",
    "use_case_membership",
    "state",
]
GraphOrigin = Literal[
    "producer_to_signal",
    "signal_to_consumer_trigger",
    "related_to",
    "derived",
    "use_case_membership",
    "state_transition",
]


@dataclass(frozen=True)
class ExplicitGraphEdge:
    """One permitted graph edge, retaining its compiled source and meaning."""

    source: str
    target: str
    meaning: GraphMeaning
    origin: GraphOrigin
    declared_by: tuple[str, ...] = ()
    label: str | None = None


@dataclass(frozen=True)
class GraphResult:
    """The entirely in-memory result of rendering one compiled model as DOT."""

    output: bytes | None = None
    diagnostic: str | None = None

    @property
    def exit_code(self) -> int:
        return 0 if self.output is not None else 1


def iter_explicit_graph_edges(
    model_or_indexes: Mapping[str, Any] | CompiledModelIndexes,
) -> Iterator[ExplicitGraphEdge]:
    """Yield only the explicit graph edges in the compiled-model order.

    A model is checked for exact consumer compatibility before its records are
    read.  Passing ``CompiledModelIndexes`` reuses indexes that were already
    built from a supported model.
    """

    if isinstance(model_or_indexes, CompiledModelIndexes):
        indexes = model_or_indexes
    else:
        if not is_supported_model(model_or_indexes):
            raise ValueError("unsupported compiled model")
        indexes = build_compiled_model_indexes(model_or_indexes)

    for signal in indexes.categories["signals"].values():
        signal_id = signal["id"]
        yield ExplicitGraphEdge(
            source=signal["producer"]["completion"],
            target=signal_id,
            meaning="causal",
            origin="producer_to_signal",
        )
        for consumer in signal["consumers"]:
            yield ExplicitGraphEdge(
                source=signal_id,
                target=consumer["trigger"],
                meaning="causal",
                origin="signal_to_consumer_trigger",
            )

    for relationship in indexes.relationships:
        source, target = relationship["endpoints"]
        is_authored = relationship["source"] == "authored"
        yield ExplicitGraphEdge(
            source=source,
            target=target,
            meaning="related_to" if is_authored else "derived",
            origin="related_to" if is_authored else "derived",
            declared_by=tuple(relationship["declared_by"]),
        )

    for membership in indexes.use_case_memberships:
        yield ExplicitGraphEdge(
            source=membership["use_case"],
            target=membership["behavior"],
            meaning="use_case_membership",
            origin="use_case_membership",
        )

    for concept in indexes.categories["concepts"].values():
        concept_id = concept["id"]
        for transition in concept["transitions"]:
            yield ExplicitGraphEdge(
                source=_state_endpoint(concept_id, transition["from"]),
                target=_state_endpoint(concept_id, transition["to"]),
                meaning="state",
                origin="state_transition",
                label=transition["completion"],
            )


def serialize_graph_dot(model_or_indexes: Mapping[str, Any] | CompiledModelIndexes) -> bytes:
    """Serialize the complete explicit graph with the approved DOT bytes."""

    edges = tuple(iter_explicit_graph_edges(model_or_indexes))
    nodes = sorted({endpoint for edge in edges for endpoint in (edge.source, edge.target)})
    lines = ["digraph pml {"]
    lines.extend(
        f"  {_dot_string(node)} [label={_dot_string(node)}];" for node in nodes
    )
    lines.extend(_dot_edge(edge) for edge in edges)
    lines.append("}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def graph_compiled_model(model: Mapping[str, Any]) -> GraphResult:
    """Render a supported compiled model or return its consumer diagnostic."""

    if not is_supported_model(model):
        return GraphResult(
            diagnostic=(
                f"[unsupported-model] {model.get('format')}@"
                f"{model.get('format_version')} is not supported"
            )
        )
    return GraphResult(output=serialize_graph_dot(build_compiled_model_indexes(model)))


def _dot_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _dot_edge(edge: ExplicitGraphEdge) -> str:
    if edge.meaning == "causal":
        attributes = '[kind="causal", style="solid"]'
    elif edge.meaning == "related_to":
        attributes = '[dir="none", kind="related_to", style="dashed"]'
    elif edge.meaning == "derived":
        attributes = '[dir="none", kind="derived", style="dashed"]'
    elif edge.meaning == "use_case_membership":
        attributes = '[dir="none", kind="use_case_membership", style="dotted"]'
    else:
        assert edge.label is not None
        attributes = (
            f'[kind="state", label={_dot_string(edge.label)}, style="solid"]'
        )
    return f"  {_dot_string(edge.source)} -> {_dot_string(edge.target)} {attributes};"


def _state_endpoint(concept_id: str, state: str) -> str:
    """Return a concept-qualified DOT node ID for one state endpoint."""

    return f"concepts.{concept_id}.states.{state}"
