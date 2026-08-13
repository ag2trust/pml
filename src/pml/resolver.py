"""Shared identity indexing and reference resolution for PML definitions."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

from pml.diagnostics import Diagnostic


OBLIGATION_SECTIONS = ("rules", "use_cases")


@dataclass(frozen=True)
class Obligation:
    """One independently addressable obligation derived from a definition."""

    id: str
    node_id: str
    section: str
    local_id: str
    definition: dict[str, Any]


ResolutionKind = Literal["signal", "feature", "use_case", "node", "architecture"]


@dataclass(frozen=True)
class ResolvedSignal:
    """One globally identified inline signal and its declaring completion."""

    id: str
    path: str
    behavior: str
    completion: str
    definition: Mapping[str, Any]


@dataclass(frozen=True)
class ResolutionStep:
    """Diagnostics produced at one authored record in traversal order."""

    kind: ResolutionKind
    path: str
    definition: Mapping[str, Any]
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True)
class ResolvedDefinition:
    """Read-only candidate tables and diagnostics for one definition snapshot."""

    actors: Mapping[str, Any]
    concepts: Mapping[str, Any]
    architecture: Mapping[str, Any]
    nodes: Mapping[str, Mapping[str, Any]]
    behaviors: Mapping[str, Mapping[str, Any]]
    use_cases: Mapping[str, Mapping[str, Any]]
    signals: Mapping[str, ResolvedSignal]
    architecture_references: Mapping[str, tuple[str, ...]]
    steps: tuple[ResolutionStep, ...]

    @property
    def diagnostics(self) -> tuple[Diagnostic, ...]:
        """Return reference diagnostics in established validation order."""

        return tuple(
            diagnostic
            for step in self.steps
            for diagnostic in step.diagnostics
        )


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _is_behavior_node(node_id: str) -> bool:
    """Return whether a semantic ID has the canonical behavior path shape."""

    parts = node_id.split(".")
    return (
        len(parts) == 6
        and parts[0] == "domains"
        and parts[2] == "features"
        and parts[4] == "behaviors"
    )


def _completion_cases(
    node: Mapping[str, Any],
) -> Iterable[tuple[str, str, dict[str, Any]]]:
    """Yield authored paths, stable obligation paths, and completion definitions."""

    outcome = node.get("outcome")
    if not isinstance(outcome, dict):
        outcome = {}
    alternatives = outcome.get("one_of")
    if isinstance(alternatives, dict):
        for alternative_id, definition in alternatives.items():
            if isinstance(definition, dict):
                yield (
                    f"outcome.one_of.{alternative_id}",
                    f"outcome.{alternative_id}",
                    definition,
                )
    elif "statement" in outcome:
        yield "outcome", "outcome", outcome
    failures = node.get("failures", {})
    if isinstance(failures, dict):
        for failure_id, definition in failures.items():
            if isinstance(definition, dict):
                path = f"failures.{failure_id}"
                yield path, path, definition


def _trigger_cases(node: Mapping[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    """Yield direct or alternative trigger paths and definitions."""

    trigger = node.get("trigger")
    if not isinstance(trigger, dict):
        return
    alternatives = trigger.get("one_of")
    if isinstance(alternatives, dict):
        for alternative_id, definition in alternatives.items():
            if isinstance(definition, dict):
                yield f"trigger.one_of.{alternative_id}", definition
    elif "statement" in trigger or "signal" in trigger:
        yield "trigger", trigger


class ReferenceResolver:
    """Resolve all definition references against one in-memory snapshot."""

    def __init__(self, document: Mapping[str, Any]) -> None:
        self._document = document

    def iter_nodes(self) -> Iterator[tuple[str, dict[str, Any]]]:
        """Yield every state-bearing rule scope, feature, and direct behavior."""

        if self._document.get("rules"):
            yield "project", {"rules": self._document["rules"]}
        for domain_id, domain in _mapping(self._document.get("domains")).items():
            if not isinstance(domain, dict):
                continue
            if domain.get("rules"):
                yield f"domains.{domain_id}", {"rules": domain["rules"]}
            for feature_id, feature in _mapping(domain.get("features")).items():
                if not isinstance(feature, dict):
                    continue
                semantic_id = f"domains.{domain_id}.features.{feature_id}"
                yield semantic_id, feature
                for behavior_id, behavior in _mapping(feature.get("behaviors")).items():
                    if isinstance(behavior, dict):
                        yield f"{semantic_id}.behaviors.{behavior_id}", behavior

    def iter_architecture(self) -> Iterator[tuple[str, dict[str, Any]]]:
        """Yield independent, flat architecture decision scopes."""

        for decision_id, decision in _mapping(self._document.get("architecture")).items():
            if isinstance(decision, dict):
                yield f"architecture.{decision_id}", decision

    def enumerate_obligations(
        self, node_id: str | None = None
    ) -> Iterator[Obligation]:
        """Yield approved stable product obligations in authored traversal order."""

        for semantic_id, node in self.iter_nodes():
            if node_id is not None and semantic_id != node_id:
                continue
            if ".behaviors." in semantic_id:
                conditions = node.get("conditions")
                if isinstance(conditions, list) and conditions:
                    yield Obligation(
                        f"{semantic_id}.conditions", semantic_id, "conditions",
                        "conditions", {"all": conditions},
                    )

                trigger = node.get("trigger")
                if isinstance(trigger, dict):
                    alternatives = trigger.get("one_of")
                    if isinstance(alternatives, dict):
                        for alternative_id, definition in alternatives.items():
                            yield Obligation(
                                f"{semantic_id}.trigger.{alternative_id}", semantic_id,
                                "trigger", alternative_id, definition,
                            )
                    else:
                        yield Obligation(
                            f"{semantic_id}.trigger", semantic_id, "trigger",
                            "trigger", trigger,
                        )

                outcome = node.get("outcome")
                failures = node.get("failures")
                if isinstance(outcome, dict):
                    alternatives = outcome.get("one_of")
                    yield Obligation(
                        f"{semantic_id}.completion", semantic_id, "completion",
                        "completion", {
                            "outcomes": list(alternatives)
                            if isinstance(alternatives, dict) else ["outcome"],
                            "failures": list(failures)
                            if isinstance(failures, dict) else [],
                        },
                    )
                    if isinstance(alternatives, dict):
                        yield Obligation(
                            f"{semantic_id}.outcome", semantic_id, "outcome",
                            "outcome", {"one_of": list(alternatives)},
                        )
                        for alternative_id, definition in alternatives.items():
                            yield Obligation(
                                f"{semantic_id}.outcome.{alternative_id}", semantic_id,
                                "outcome", alternative_id, definition,
                            )
                    else:
                        yield Obligation(
                            f"{semantic_id}.outcome", semantic_id, "outcome",
                            "outcome", outcome,
                        )

                if isinstance(failures, dict):
                    for failure_id, definition in failures.items():
                        yield Obligation(
                            f"{semantic_id}.failures.{failure_id}", semantic_id,
                            "failures", failure_id, definition,
                        )
            for section in OBLIGATION_SECTIONS:
                for local_id, definition in _mapping(node.get(section)).items():
                    yield Obligation(
                        f"{semantic_id}.{section}.{local_id}", semantic_id, section,
                        local_id, definition,
                    )

    def enumerate_architecture_obligations(
        self, node_id: str | None = None
    ) -> Iterator[Obligation]:
        """Yield architecture constraints without mixing them into product scopes."""

        for semantic_id, decision in self.iter_architecture():
            if node_id is not None and semantic_id != node_id:
                continue
            for local_id, definition in _mapping(decision.get("constraints")).items():
                yield Obligation(
                    f"{semantic_id}.constraints.{local_id}", semantic_id,
                    "constraints", local_id, definition,
                )

    def resolve(self) -> ResolvedDefinition:
        actors = _mapping(self._document.get("actors"))
        concepts = _mapping(self._document.get("concepts"))
        architecture = _mapping(self._document.get("architecture"))
        actor_ids = set(actors)
        concept_ids = set(concepts)
        architecture_ids = set(architecture)

        # Invalid authored IDs can derive the same path. Candidate lookup is
        # unique, but diagnostics must still traverse every authored record.
        node_entries = tuple(self.iter_nodes())
        nodes = dict(node_entries)
        behavior_ids = {
            node_id for node_id in nodes if _is_behavior_node(node_id)
        }
        behaviors = {
            node_id: node for node_id, node in nodes.items() if node_id in behavior_ids
        }
        node_ids = set(nodes)
        signals: dict[str, ResolvedSignal] = {}
        use_cases: dict[str, Mapping[str, Any]] = {}
        referenced_architecture: dict[str, list[str]] = {}
        steps: list[ResolutionStep] = []

        # Signals are indexed before trigger references are checked so a producer
        # may appear after its consumer in authored map order.
        for node_id, node in node_entries:
            if node_id not in behavior_ids:
                continue
            for authored_path, obligation_path, completion in _completion_cases(node):
                signal = completion.get("signal")
                if not isinstance(signal, dict):
                    continue
                signal_path = f"{node_id}.{authored_path}.signal"
                signal_diagnostics: list[Diagnostic] = []
                signal_id = signal.get("id")
                if isinstance(signal_id, str):
                    prior = signals.get(signal_id)
                    if prior is not None:
                        signal_diagnostics.append(
                            Diagnostic(
                                f"{signal_path}.id",
                                "duplicate-signal",
                                f"signal '{signal_id}' is already defined at {prior.path}",
                            )
                        )
                    else:
                        signals[signal_id] = ResolvedSignal(
                            id=signal_id,
                            path=signal_path,
                            behavior=node_id,
                            completion=f"{node_id}.{obligation_path}",
                            definition=MappingProxyType(signal),
                        )
                subject = signal.get("subject")
                if isinstance(subject, str) and subject not in concept_ids:
                    signal_diagnostics.append(
                        Diagnostic(
                            f"{signal_path}.subject",
                            "undefined-reference",
                            f"unknown concept '{subject}'",
                        )
                    )
                steps.append(
                    ResolutionStep(
                        "signal",
                        signal_path,
                        MappingProxyType(signal),
                        tuple(signal_diagnostics),
                    )
                )

        for domain_id, domain in _mapping(self._document.get("domains")).items():
            if not isinstance(domain, dict):
                continue
            for feature_id, feature in _mapping(domain.get("features")).items():
                if not isinstance(feature, dict):
                    continue
                prefix = f"domains.{domain_id}.features.{feature_id}"
                feature_diagnostics: list[Diagnostic] = []
                for actor in feature.get("actors", []):
                    if actor not in actor_ids:
                        feature_diagnostics.append(
                            Diagnostic(
                                f"{prefix}.actors",
                                "undefined-reference",
                                f"unknown actor '{actor}'",
                            )
                        )
                steps.append(
                    ResolutionStep(
                        "feature",
                        prefix,
                        MappingProxyType(feature),
                        tuple(feature_diagnostics),
                    )
                )
                for use_case_id, use_case in _mapping(feature.get("use_cases")).items():
                    if not isinstance(use_case, dict):
                        continue
                    use_case_path = f"{prefix}.use_cases.{use_case_id}"
                    use_cases[use_case_path] = use_case
                    use_case_diagnostics: list[Diagnostic] = []
                    actor = use_case.get("actor")
                    if actor and actor not in actor_ids:
                        use_case_diagnostics.append(
                            Diagnostic(
                                f"{use_case_path}.actor",
                                "undefined-reference",
                                f"unknown actor '{actor}'",
                            )
                        )
                    referenced_behaviors = use_case.get("behaviors", [])
                    if isinstance(referenced_behaviors, list):
                        for behavior in referenced_behaviors:
                            if isinstance(behavior, str) and behavior not in behavior_ids:
                                use_case_diagnostics.append(
                                    Diagnostic(
                                        f"{use_case_path}.behaviors",
                                        "undefined-reference",
                                        f"unknown behavior '{behavior}'",
                                    )
                                )
                    steps.append(
                        ResolutionStep(
                            "use_case",
                            use_case_path,
                            MappingProxyType(use_case),
                            tuple(use_case_diagnostics),
                        )
                    )

        signal_ids = set(signals)
        for node_id, node in node_entries:
            node_diagnostics: list[Diagnostic] = []
            related_nodes = node.get("related_to", [])
            if isinstance(related_nodes, list):
                for related in related_nodes:
                    if not isinstance(related, str):
                        continue
                    if related not in node_ids:
                        node_diagnostics.append(
                            Diagnostic(
                                f"{node_id}.related_to",
                                "undefined-reference",
                                f"unknown node '{related}'",
                            )
                        )
                    elif related == node_id:
                        node_diagnostics.append(
                            Diagnostic(
                                f"{node_id}.related_to",
                                "self-reference",
                                "a node cannot relate to itself",
                            )
                        )
            if node_id in behavior_ids:
                for trigger_path, trigger in _trigger_cases(node):
                    signal = trigger.get("signal")
                    if isinstance(signal, str) and signal not in signal_ids:
                        node_diagnostics.append(
                            Diagnostic(
                                f"{node_id}.{trigger_path}.signal",
                                "undefined-reference",
                                f"unknown signal '{signal}'",
                            )
                        )
            node_architecture = node.get("architecture", [])
            if node_id not in behavior_ids and isinstance(node_architecture, list):
                for decision in node_architecture:
                    if not isinstance(decision, str):
                        continue
                    referenced_architecture.setdefault(decision, []).append(node_id)
                    if decision not in architecture_ids:
                        node_diagnostics.append(
                            Diagnostic(
                                f"{node_id}.architecture",
                                "undefined-reference",
                                f"unknown architecture decision '{decision}'",
                            )
                        )
            steps.append(
                ResolutionStep(
                    "node",
                    node_id,
                    MappingProxyType(node),
                    tuple(node_diagnostics),
                )
            )

        for decision_id, decision in architecture.items():
            if not isinstance(decision, dict):
                continue
            prefix = f"architecture.{decision_id}"
            architecture_diagnostics: list[Diagnostic] = []
            if decision_id not in referenced_architecture:
                architecture_diagnostics.append(
                    Diagnostic(
                        prefix,
                        "unreferenced-architecture",
                        "architecture decision is not referenced by a feature",
                    )
                )
            steps.append(
                ResolutionStep(
                    "architecture",
                    prefix,
                    MappingProxyType(decision),
                    tuple(architecture_diagnostics),
                )
            )

        return ResolvedDefinition(
            actors=MappingProxyType(dict(actors)),
            concepts=MappingProxyType(dict(concepts)),
            architecture=MappingProxyType(dict(architecture)),
            nodes=MappingProxyType(nodes),
            behaviors=MappingProxyType(behaviors),
            use_cases=MappingProxyType(use_cases),
            signals=MappingProxyType(signals),
            architecture_references=MappingProxyType(
                {
                    decision_id: tuple(references)
                    for decision_id, references in referenced_architecture.items()
                }
            ),
            steps=tuple(steps),
        )


def resolve_references(document: Mapping[str, Any]) -> ResolvedDefinition:
    """Resolve references in one PML definition using the shared resolver."""

    return ReferenceResolver(document).resolve()


# ``Resolver`` and the module-level helpers preserve the previous obligation
# consumer surface while ensuring every derivation uses ReferenceResolver.
Resolver = ReferenceResolver


def resolve(document: Mapping[str, Any]) -> ReferenceResolver:
    """Create the shared resolver for one already-loaded PML definition."""

    return ReferenceResolver(document)


def iter_nodes(document: Mapping[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield semantic nodes through the shared resolver."""

    yield from resolve(document).iter_nodes()


def iter_architecture(
    document: Mapping[str, Any],
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield architecture scopes through the shared resolver."""

    yield from resolve(document).iter_architecture()


def enumerate_obligations(
    document: Mapping[str, Any], node_id: str | None = None
) -> Iterator[Obligation]:
    """Enumerate product obligations through the shared resolver."""

    yield from resolve(document).enumerate_obligations(node_id)


def enumerate_architecture_obligations(
    document: Mapping[str, Any], node_id: str | None = None
) -> Iterator[Obligation]:
    """Enumerate architecture obligations through the shared resolver."""

    yield from resolve(document).enumerate_architecture_obligations(node_id)
