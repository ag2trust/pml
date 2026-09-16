"""Restricted-YAML, structural, reference, and language validation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
import copy
import json
from pathlib import Path
import re
from typing import Any, Iterable

from jsonschema import Draft202012Validator
import yaml

from pml.compiled_model import CompiledModel
from pml.coupling import signal_coupling_warnings
from pml.diagnostics import Diagnostic
from pml.resolver import ReferenceResolver, ResolvedDefinition, resolve_references


AMBIGUOUS_WORDS = (
    "appropriately",
    "etc",
    "normally",
    "properly",
    "relevant",
    "seamlessly",
    "should",
)
NORMATIVE_MARKER = re.compile(r"\b(MUST|MUST NOT)\b")
SURFACE_NORMATIVE_MARKER = re.compile(r"\b(MUST NOT|MUST|SHALL|SHOULD)\b")
ARCHITECTURE_IMPLEMENTATION_DETAIL = re.compile(
    r"(?:\b(?:file|filename|function|class|table|endpoint|topology|cluster|service)\b|(?-i:\bnode\b)|"
    r"\b(?:get|post|put|patch|delete)\s+/|(?-i:\b[a-z0-9_-]+\.(?:py|js|ts|java|go|rb|sql|ya?ml|json)\b)|"
    r"(?-i:\b[a-z][A-Za-z0-9_]*\([^)]*\))|\b[A-Za-z][A-Za-z0-9_]*\s*:\s*\S+|"
    r"\b[A-Za-z_][A-Za-z0-9_.-]*\s*=\s*\S+|\{\s*\"(?:[^\"\\\\]|\\\\.)+\"\s*:)",
    re.IGNORECASE,
)
TRANSITION_IMPLEMENTATION_DETAIL = re.compile(
    r"(?:\b(?:files?|filenames?|functions?|class(?:es)?|components?|tables?|databases?|"
    r"endpoints?|(?:REST\s+)?APIs?|framework(?:s|\s+elements?)?|hooks?|librar(?:y|ies)|methods?|modules?|"
    r"services?|jobs?|queues?|tests?|payload\s+schemas?)\b|"
    r"\b(?:get|post|put|patch|delete)\s+/|"
    r"(?-i:\b[a-z0-9_-]+\.(?:py|js|ts|java|go|rb|sql|ya?ml|json)\b)|"
    r"(?-i:\b[a-z][A-Za-z0-9_]*\([^)]*\))|"
    r"\b[A-Za-z_][A-Za-z0-9_.-]*\s*=\s*\S+|"
    r"\{\s*\"(?:[^\"\\\\]|\\\\.)+\"\s*:)",
    re.IGNORECASE,
)


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader rejecting aliases, duplicate keys, and implicit dates."""

    def compose_node(self, parent: Any, index: Any) -> yaml.Node:
        if self.check_event(yaml.AliasEvent):
            event = self.peek_event()
            raise yaml.constructor.ConstructorError(
                None, None, f"aliases are forbidden ({event.anchor})", event.start_mark
            )
        return super().compose_node(parent, index)


class _LoadingError(yaml.YAMLError):
    """A restricted-YAML well-formedness failure with a source mark."""

    def __init__(self, code: str, message: str, mark: yaml.error.Mark) -> None:
        self.code = code
        self.message = message
        self.mark = mark


# PML treats words such as "on" and "no" as strings. Only true/false are booleans.
UniqueKeyLoader.yaml_implicit_resolvers = copy.deepcopy(
    yaml.SafeLoader.yaml_implicit_resolvers
)
for first, resolvers in UniqueKeyLoader.yaml_implicit_resolvers.items():
    UniqueKeyLoader.yaml_implicit_resolvers[first] = [
        item for item in resolvers
        if item[0] != "tag:yaml.org,2002:bool"
    ]
UniqueKeyLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false)$", re.IGNORECASE),
    list("tTfF"),
)


def _yaml_type_name(value: Any) -> str:
    """Return the YAML type name used in loading diagnostics."""

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "sequence"
    if isinstance(value, dict):
        return "mapping"
    return type(value).__name__


def _construct_string(loader: UniqueKeyLoader, node: yaml.ScalarNode) -> str:
    value = loader.construct_scalar(node)
    for character in value:
        if 0xD800 <= ord(character) <= 0xDFFF:
            raise _LoadingError(
                "invalid-unicode-scalar",
                f"string contains invalid Unicode scalar U+{ord(character):04X}",
                node.start_mark,
            )
    return value


def _construct_mapping_key(loader: UniqueKeyLoader, node: yaml.Node) -> str:
    """Construct one YAML mapping key under the scalar-string precondition."""

    key = loader.construct_object(node, deep=False)
    if not isinstance(key, str):
        raise _LoadingError(
            "non-string-key",
            f"mapping key decodes to YAML {_yaml_type_name(key)}",
            node.start_mark,
        )
    return key


def _construct_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    mapping: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = _construct_mapping_key(loader, key_node)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key: {key}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


def _construct_set(loader: UniqueKeyLoader, node: yaml.MappingNode) -> Iterable[set[str]]:
    """Construct a YAML set while enforcing its mapping-key precondition."""

    result: set[str] = set()
    yield result
    if not isinstance(node, yaml.MappingNode):
        raise yaml.constructor.ConstructorError(
            "while constructing a set", node.start_mark,
            f"expected a mapping node, but found {node.id}", node.start_mark,
        )
    loader.flatten_mapping(node)
    for key_node, value_node in node.value:
        result.add(_construct_mapping_key(loader, key_node))
        loader.construct_object(value_node)


def _construct_pairs(
    loader: UniqueKeyLoader, node: yaml.SequenceNode, tag_name: str
) -> Iterable[list[tuple[str, Any]]]:
    """Construct YAML ordered maps and pairs with string-only keys."""

    result: list[tuple[str, Any]] = []
    yield result
    if not isinstance(node, yaml.SequenceNode):
        raise yaml.constructor.ConstructorError(
            f"while constructing {tag_name}", node.start_mark,
            f"expected a sequence, but found {node.id}", node.start_mark,
        )
    for subnode in node.value:
        if not isinstance(subnode, yaml.MappingNode):
            raise yaml.constructor.ConstructorError(
                f"while constructing {tag_name}", node.start_mark,
                f"expected a mapping of length 1, but found {subnode.id}", subnode.start_mark,
            )
        if len(subnode.value) != 1:
            raise yaml.constructor.ConstructorError(
                f"while constructing {tag_name}", node.start_mark,
                f"expected a single mapping item, but found {len(subnode.value)} items",
                subnode.start_mark,
            )
        key_node, value_node = subnode.value[0]
        result.append((_construct_mapping_key(loader, key_node), loader.construct_object(value_node)))


def _construct_omap(loader: UniqueKeyLoader, node: yaml.SequenceNode) -> Iterable[list[tuple[str, Any]]]:
    yield from _construct_pairs(loader, node, "an ordered map")


def _construct_yaml_pairs(loader: UniqueKeyLoader, node: yaml.SequenceNode) -> Iterable[list[tuple[str, Any]]]:
    yield from _construct_pairs(loader, node, "pairs")


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)
UniqueKeyLoader.add_constructor("tag:yaml.org,2002:str", _construct_string)
UniqueKeyLoader.add_constructor("tag:yaml.org,2002:set", _construct_set)
UniqueKeyLoader.add_constructor("tag:yaml.org,2002:omap", _construct_omap)
UniqueKeyLoader.add_constructor("tag:yaml.org,2002:pairs", _construct_yaml_pairs)


def _schema() -> dict[str, Any]:
    schema_path = Path(__file__).resolve().parents[2] / "schema" / "pml.schema.json"
    return json.loads(schema_path.read_text())


def _path(parts: Iterable[Any]) -> str:
    rendered = ""
    for part in parts:
        if isinstance(part, int):
            rendered += f"[{part}]"
        else:
            rendered += ("." if rendered else "") + str(part)
    return rendered or "$"


def _walk(value: Any, path: tuple[Any, ...] = ()) -> Iterable[tuple[tuple[Any, ...], Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, path + (index,))


def _cardinality_warnings(document: dict[str, Any]) -> list[Diagnostic]:
    """Return deterministic advisory diagnostics for authored map sizes."""

    warnings: list[Diagnostic] = []
    for parts, value in _walk(document):
        if not isinstance(value, dict):
            continue
        is_rules_map = (
            parts == ("rules",)
            or (
                len(parts) == 3
                and parts[0] == "domains"
                and parts[2] == "rules"
            )
            or (
                len(parts) == 5
                and parts[0] == "domains"
                and parts[2] == "features"
                and parts[4] == "rules"
            )
            or (
                len(parts) == 7
                and parts[0] == "domains"
                and parts[2] == "features"
                and parts[4] == "behaviors"
                and parts[6] == "rules"
            )
            or (
                len(parts) == 3
                and parts[0] == "architecture"
                and parts[2] == "constraints"
            )
        )
        if is_rules_map and len(value) > 7:
            warnings.append(
                Diagnostic(
                    _path(parts),
                    "PML-W-RULE-COUNT",
                    "rules maps should contain no more than 7 rules",
                    severity="warning",
                )
            )
        if (
            len(parts) == 5
            and parts[0] == "domains"
            and parts[2] == "features"
            and parts[4] == "behaviors"
            and len(value) > 7
        ):
            warnings.append(
                Diagnostic(
                    _path(parts),
                    "PML-W-BEHAVIOR-COUNT",
                    "features should contain no more than 7 behaviors",
                    severity="warning",
                )
            )
    return sorted(warnings, key=lambda diagnostic: diagnostic.path)


def _term_pattern(term: str) -> re.Pattern[str]:
    """Compile a case-insensitive whole-word pattern for one PML term."""

    normalized = term.casefold().replace("_", " ")
    return re.compile(rf"(?<!\w){re.escape(normalized)}(?!\w)")


def _mentioned_terms(text: str, terms: dict[str, re.Pattern[str]]) -> set[str]:
    """Return canonical terms mentioned by a statement."""

    normalized = text.casefold().replace("_", " ")
    return {term for term, pattern in terms.items() if pattern.search(normalized)}


def _behavior_texts(behavior: dict[str, Any]) -> Iterable[str]:
    """Yield the authored statements that make a behavior's terms local."""

    conditions = behavior.get("conditions")
    if isinstance(conditions, dict):
        for statement in conditions.get("statements", []):
            if isinstance(statement, str):
                yield statement
            elif isinstance(statement, dict):
                concept = statement.get("concept")
                state = statement.get("state")
                if isinstance(concept, str):
                    yield concept
                if isinstance(state, str):
                    yield state

    trigger = behavior.get("trigger")
    if isinstance(trigger, dict):
        cases = trigger.get("cases") if trigger.get("kind") == "one_of" else [trigger.get("case")]
        if isinstance(cases, list):
            for case in cases:
                if isinstance(case, dict) and isinstance(case.get("statement"), str):
                    yield case["statement"]

    outcome = behavior.get("outcome")
    if isinstance(outcome, dict):
        cases = outcome.get("cases") if outcome.get("kind") == "one_of" else [outcome.get("case")]
        if isinstance(cases, list):
            for case in cases:
                if isinstance(case, dict) and isinstance(case.get("statement"), str):
                    yield case["statement"]

    for failure in behavior.get("failures", []):
        if isinstance(failure, dict) and isinstance(failure.get("statement"), str):
            yield failure["statement"]


def _rule_scope_warnings(model: CompiledModel) -> list[Diagnostic]:
    """Return deterministic rule-scope advice derived solely from a compiled model."""

    term_groups = {
        "actor": {actor["id"] for actor in model["actors"]},
        "concept": {concept["id"] for concept in model["concepts"]},
        "vocabulary": {entry["term"] for entry in model["vocabulary"]},
        "behavior": {behavior["id"] for behavior in model["behaviors"]},
    }
    terms = {
        term: _term_pattern(term)
        for group in term_groups.values()
        for term in group
    }
    features = {feature["path"]: feature for feature in model["features"]}
    behaviors_by_feature: dict[str, list[dict[str, Any]]] = {}
    for behavior in model["behaviors"]:
        behaviors_by_feature.setdefault(behavior["feature"], []).append(behavior)
    use_cases_by_feature: dict[str, list[dict[str, Any]]] = {}
    for use_case in model["use_cases"]:
        use_cases_by_feature.setdefault(use_case["feature"], []).append(use_case)

    feature_terms: dict[str, set[str]] = {}
    for feature_path, feature in features.items():
        local = set(feature["actors"])
        for behavior in behaviors_by_feature.get(feature_path, []):
            local.add(behavior["id"])
            for statement in _behavior_texts(behavior):
                local.update(_mentioned_terms(statement, terms))
        for use_case in use_cases_by_feature.get(feature_path, []):
            for value in (use_case["actor"], use_case["goal"]):
                local.update(_mentioned_terms(value, terms))
        feature_terms[feature_path] = local

    domain_terms: dict[str, set[str]] = {domain["path"]: set() for domain in model["domains"]}
    for feature in model["features"]:
        domain_terms[feature["domain"]].update(feature_terms[feature["path"]])

    warnings: list[Diagnostic] = []
    for obligation in sorted(model["obligations"], key=lambda item: item["id"]):
        if obligation["kind"] != "rule":
            continue
        node = obligation["node"]
        if node in feature_terms:
            local = feature_terms[node]
            message = "rule mentions no term used in this feature; consider domain or project scope"
        elif node in domain_terms:
            local = domain_terms[node]
            message = "rule mentions no term used in this domain; consider project scope"
        else:
            continue
        statement = obligation["definition"]["statement"]
        mentioned = _mentioned_terms(statement, terms)
        if mentioned and not mentioned.intersection(local):
            warnings.append(
                Diagnostic(
                    obligation["id"],
                    "PML-W-RULE-SCOPE",
                    message,
                    severity="warning",
                )
            )
    return warnings


def _is_transition_text(parts: tuple[Any, ...]) -> bool:
    """Return whether text is normative by its position in a behavior transition."""

    return (
        len(parts) == 8
        and parts[0] == "domains"
        and parts[2] == "features"
        and parts[4] == "behaviors"
        and parts[6] in {"trigger", "outcome"}
        and parts[7] == "statement"
    ) or (
        len(parts) == 10
        and parts[0] == "domains"
        and parts[2] == "features"
        and parts[4] == "behaviors"
        and parts[6] in {"trigger", "outcome"}
        and parts[7] == "one_of"
        and parts[9] == "statement"
    ) or (
        len(parts) == 9
        and parts[0] == "domains"
        and parts[2] == "features"
        and parts[4] == "behaviors"
        and parts[6] == "failures"
        and parts[8] == "statement"
    ) or (
        len(parts) == 8
        and parts[0] == "domains"
        and parts[2] == "features"
        and parts[4] == "behaviors"
        and parts[6] == "conditions"
        and isinstance(parts[7], int)
    )


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _keys(value: Any) -> list[str]:
    return list(_mapping(value).keys())


@dataclass(frozen=True)
class _ShowTargetIndex:
    """Canonical `shows` paths plus feature-local bare-ID resolution."""

    paths: frozenset[str]
    bare_paths: dict[tuple[str, str], str | None]


def _eligible_show_targets(document: dict[str, Any]) -> _ShowTargetIndex:
    """Index every obligation path a surface `shows` may resolve to.

    A bare ID is valid only when it has one eligible terminal-path match in its
    enclosing feature. Record that result while enumerating targets so each
    surface state performs constant-time lookup instead of rescanning every
    obligation in the definition.
    """

    paths: set[str] = set()
    bare_paths: dict[tuple[str, str], str | None] = {}

    def add(path: str, feature_path: str | None = None) -> None:
        paths.add(path)
        if feature_path is None:
            return
        key = (feature_path, path.rsplit(".", 1)[-1])
        prior = bare_paths.get(key)
        if prior is None and key in bare_paths:
            return
        bare_paths[key] = path if prior is None else None

    for rule_id in _keys(document.get("rules")):
        add(f"project.rules.{rule_id}")
    for domain_id, domain in _mapping(document.get("domains")).items():
        if not isinstance(domain, dict):
            continue
        for rule_id in _keys(domain.get("rules")):
            add(f"domains.{domain_id}.rules.{rule_id}")
        for feature_id, feature in _mapping(domain.get("features")).items():
            if not isinstance(feature, dict):
                continue
            feature_path = f"domains.{domain_id}.features.{feature_id}"
            for rule_id in _keys(feature.get("rules")):
                add(f"{feature_path}.rules.{rule_id}", feature_path)
            for behavior_id, behavior in _mapping(feature.get("behaviors")).items():
                if not isinstance(behavior, dict):
                    continue
                behavior_path = f"{feature_path}.behaviors.{behavior_id}"
                for rule_id in _keys(behavior.get("rules")):
                    add(f"{behavior_path}.rules.{rule_id}", feature_path)
                outcome = behavior.get("outcome")
                if isinstance(outcome, dict):
                    alternatives = outcome.get("one_of")
                    if isinstance(alternatives, dict):
                        for alternative_id in alternatives:
                            add(
                                f"{behavior_path}.outcome.{alternative_id}",
                                feature_path,
                            )
                    elif "statement" in outcome:
                        add(f"{behavior_path}.outcome", feature_path)
                failures = behavior.get("failures")
                if isinstance(failures, dict):
                    for failure_id in failures:
                        add(
                            f"{behavior_path}.failures.{failure_id}",
                            feature_path,
                        )
    return _ShowTargetIndex(frozenset(paths), bare_paths)


def resolve_show_entry(
    entry: str, feature_path: str, eligible: _ShowTargetIndex
) -> str | None:
    """Resolve one authored `shows` entry to a canonical obligation path.

    Accepted forms, tried in order:
      1. Full obligation path already present in ``eligible``.
      2. Feature-relative path prepended to ``feature_path``.
      3. Behavior-relative path (missing the leading ``behaviors.``).
      4. Bare last-segment ID with exactly one match within the feature.
    """

    if entry in eligible.paths:
        return entry
    prefixed = f"{feature_path}.{entry}"
    if prefixed in eligible.paths:
        return prefixed
    behavior_prefixed = f"{feature_path}.behaviors.{entry}"
    if behavior_prefixed in eligible.paths:
        return behavior_prefixed
    return eligible.bare_paths.get((feature_path, entry))


def _surface_diagnostics(document: dict[str, Any]) -> list[Diagnostic]:
    """Reject normative markers, unresolved paths, and duplicate `shows`."""

    diagnostics: list[Diagnostic] = []
    eligible = _eligible_show_targets(document)
    domains = _mapping(document.get("domains"))
    for domain_id, domain in domains.items():
        if not isinstance(domain, dict):
            continue
        for feature_id, feature in _mapping(domain.get("features")).items():
            if not isinstance(feature, dict):
                continue
            feature_path = f"domains.{domain_id}.features.{feature_id}"
            experience = feature.get("experience")
            if not isinstance(experience, dict):
                continue
            surfaces = experience.get("surfaces")
            if not isinstance(surfaces, dict):
                continue
            for surface_id, surface in surfaces.items():
                if not isinstance(surface, dict):
                    continue
                surface_path = (
                    f"{feature_path}.experience.surfaces.{surface_id}"
                )
                for parts, value in _walk(surface, (surface_path,)):
                    if not isinstance(value, str):
                        continue
                    if SURFACE_NORMATIVE_MARKER.search(value):
                        diagnostics.append(
                            Diagnostic(
                                _path(parts),
                                "PML-E-SURFACE-NORMATIVE",
                                "surfaces reference obligations instead of restating them; remove normative markers",
                            )
                        )
                states = surface.get("states")
                if not isinstance(states, dict):
                    continue
                for state_id, state in states.items():
                    if not isinstance(state, dict):
                        continue
                    shows = state.get("shows")
                    if not isinstance(shows, list):
                        continue
                    state_path = (
                        f"{surface_path}.states.{state_id}.shows"
                    )
                    resolved_by_index: dict[int, str] = {}
                    for index, entry in enumerate(shows):
                        if not isinstance(entry, str):
                            continue
                        resolved = resolve_show_entry(
                            entry, feature_path, eligible
                        )
                        if resolved is None:
                            diagnostics.append(
                                Diagnostic(
                                    f"{state_path}[{index}]",
                                    "undefined-reference",
                                    f"'{entry}' does not resolve to a rule, outcome, outcome alternative, or failure in the enclosing feature or the definition",
                                )
                            )
                            continue
                        resolved_by_index[index] = resolved
                    seen: dict[str, int] = {}
                    for index, resolved in resolved_by_index.items():
                        if resolved in seen:
                            diagnostics.append(
                                Diagnostic(
                                    f"{state_path}[{index}]",
                                    "duplicate-reference",
                                    f"'{shows[index]}' resolves to the same obligation as '{shows[seen[resolved]]}'",
                                )
                            )
                        else:
                            seen[resolved] = index
    return diagnostics


def _condition_diagnostics(document: dict[str, Any]) -> list[Diagnostic]:
    """Reject unknown concepts, undeclared states, and duplicate concept conditions."""

    diagnostics: list[Diagnostic] = []
    concepts = _mapping(document.get("concepts"))
    concept_states: dict[str, list[str]] = {}
    for concept_id, definition in concepts.items():
        if not isinstance(definition, dict):
            continue
        states = definition.get("states")
        concept_states[concept_id] = (
            list(states) if isinstance(states, list) else []
        )

    for domain_id, domain in _mapping(document.get("domains")).items():
        if not isinstance(domain, dict):
            continue
        for feature_id, feature in _mapping(domain.get("features")).items():
            if not isinstance(feature, dict):
                continue
            for behavior_id, behavior in _mapping(feature.get("behaviors")).items():
                if not isinstance(behavior, dict):
                    continue
                conditions = behavior.get("conditions")
                if not isinstance(conditions, list):
                    continue
                base = (
                    f"domains.{domain_id}.features.{feature_id}"
                    f".behaviors.{behavior_id}.conditions"
                )
                seen_concepts: dict[str, int] = {}
                for index, item in enumerate(conditions):
                    if not isinstance(item, dict):
                        continue
                    concept = item.get("concept")
                    state = item.get("state")
                    if isinstance(concept, str) and concept not in concept_states:
                        diagnostics.append(
                            Diagnostic(
                                f"{base}[{index}].concept",
                                "PML-E-CONDITION-CONCEPT",
                                f"unknown concept '{concept}'",
                            )
                        )
                    elif (
                        isinstance(concept, str)
                        and isinstance(state, str)
                        and state not in concept_states[concept]
                    ):
                        diagnostics.append(
                            Diagnostic(
                                f"{base}[{index}].state",
                                "PML-E-CONDITION-STATE",
                                f"concept '{concept}' does not declare state '{state}'",
                            )
                        )
                    if isinstance(concept, str):
                        if concept in seen_concepts:
                            diagnostics.append(
                                Diagnostic(
                                    f"{base}[{index}].concept",
                                    "PML-E-CONDITION-CONCEPT",
                                    (
                                        f"concept '{concept}' appears in another "
                                        f"structured condition at index "
                                        f"{seen_concepts[concept]}"
                                    ),
                                )
                            )
                        else:
                            seen_concepts[concept] = index
    return diagnostics


def _completion_cases(
    document: dict[str, Any],
) -> Iterable[tuple[str, dict[str, Any]]]:
    """Yield every direct completion with its canonical obligation path."""

    for domain_id, domain in sorted(_mapping(document.get("domains")).items()):
        if not isinstance(domain, dict):
            continue
        for feature_id, feature in sorted(_mapping(domain.get("features")).items()):
            if not isinstance(feature, dict):
                continue
            for behavior_id, behavior in sorted(
                _mapping(feature.get("behaviors")).items()
            ):
                if not isinstance(behavior, dict):
                    continue
                behavior_path = (
                    f"domains.{domain_id}.features.{feature_id}"
                    f".behaviors.{behavior_id}"
                )
                outcome = behavior.get("outcome")
                if isinstance(outcome, dict):
                    alternatives = outcome.get("one_of")
                    if isinstance(alternatives, dict):
                        for outcome_id, definition in sorted(alternatives.items()):
                            if isinstance(definition, dict):
                                yield f"{behavior_path}.outcome.{outcome_id}", definition
                    else:
                        yield f"{behavior_path}.outcome", outcome
                for failure_id, definition in sorted(
                    _mapping(behavior.get("failures")).items()
                ):
                    if isinstance(definition, dict):
                        yield f"{behavior_path}.failures.{failure_id}", definition


def _transition_diagnostics(document: dict[str, Any]) -> list[Diagnostic]:
    """Resolve authored state-transition endpoints against declared concepts."""

    concepts = _mapping(document.get("concepts"))
    concept_states = {
        concept_id: (
            list(definition["states"])
            if isinstance(definition.get("states"), list)
            else []
        )
        for concept_id, definition in concepts.items()
        if isinstance(definition, dict)
    }
    diagnostics: list[Diagnostic] = []
    for completion_path, completion in _completion_cases(document):
        transitions = completion.get("transitions")
        if not isinstance(transitions, dict):
            continue
        for concept_id, value in sorted(transitions.items()):
            path = f"{completion_path}.transitions.{concept_id}"
            if concept_id not in concept_states:
                diagnostics.append(
                    Diagnostic(
                        path,
                        "PML-E-TRANSITION-CONCEPT",
                        f"unknown concept '{concept_id}'",
                    )
                )
                continue
            if not isinstance(value, str):
                continue
            endpoints = value.split(" -> ")
            if len(endpoints) != 2:
                continue
            from_state, to_state = endpoints
            declared = concept_states[concept_id]
            invalid: list[str] = []
            if from_state not in {"*", "none"} and from_state not in declared:
                invalid.append(from_state)
            if to_state != "none" and to_state not in declared:
                invalid.append(to_state)
            if invalid:
                diagnostics.append(
                    Diagnostic(
                        path,
                        "PML-E-TRANSITION-STATE",
                        (
                            f"concept '{concept_id}' does not declare state "
                            f"'{invalid[0]}'"
                        ),
                    )
                )
                continue
            if from_state == to_state:
                diagnostics.append(
                    Diagnostic(
                        path,
                        "PML-E-TRANSITION-STATE",
                        "transition from and to states must differ",
                    )
                )
    return diagnostics


def _state_transition_warnings(model: CompiledModel) -> list[Diagnostic]:
    """Return complete-definition reachability advice for declared state machines."""

    concepts = {concept["id"]: concept for concept in model["concepts"]}
    warnings: list[Diagnostic] = []
    for concept_id, concept in sorted(concepts.items()):
        transitions = concept["transitions"]
        if not transitions:
            continue
        produced = {
            transition["to"]
            for transition in transitions
            if transition["to"] != "none"
        }
        outgoing = {transition["from"] for transition in transitions}
        for index, state in enumerate(concept["states"]):
            path = f"concepts.{concept_id}.states[{index}]"
            if state not in produced:
                warnings.append(
                    Diagnostic(
                        path,
                        "PML-W-STATE-UNREACHABLE",
                        f"declared state '{state}' has no completion transition into it",
                        severity="warning",
                    )
                )
            if state not in outgoing and "*" not in outgoing:
                warnings.append(
                    Diagnostic(
                        path,
                        "PML-W-STATE-DEAD-END",
                        (
                            f"declared state '{state}' has no completion transition "
                            "out of it or into none"
                        ),
                        severity="warning",
                    )
                )

    for behavior in model["behaviors"]:
        conditions = behavior.get("conditions")
        if not isinstance(conditions, dict):
            continue
        for index, condition in enumerate(conditions["statements"]):
            if not isinstance(condition, dict):
                continue
            concept_id = condition["concept"]
            state = condition["state"]
            concept = concepts[concept_id]
            if not concept["transitions"]:
                continue
            if any(
                transition["to"] == state
                for transition in concept["transitions"]
            ):
                continue
            warnings.append(
                Diagnostic(
                    f"{behavior['path']}.conditions[{index}].state",
                    "PML-W-CONDITION-STATE-UNPRODUCED",
                    (
                        f"condition requires state '{state}' of concept '{concept_id}', "
                        "but no completion transition produces it"
                    ),
                    severity="warning",
                )
            )
    return sorted(warnings, key=lambda diagnostic: (diagnostic.path, diagnostic.code))


def _semantic_diagnostics(
    document: dict[str, Any],
    resolution: ResolvedDefinition | None = None,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    vocabulary_map = _mapping(document.get("vocabulary"))
    actors_map = _mapping(document.get("actors"))
    concepts_map = _mapping(document.get("concepts"))

    declared_terms: dict[str, tuple[str, str]] = {}
    for source_kind, definitions in (
        ("actor", actors_map),
        ("concept", concepts_map),
    ):
        for identifier in definitions:
            declared_terms.setdefault(
                identifier.casefold().replace("_", " "),
                (source_kind, identifier),
            )
    for term in vocabulary_map:
        duplicate = declared_terms.get(term.casefold().replace("_", " "))
        if duplicate is not None:
            source_kind, identifier = duplicate
            diagnostics.append(
                Diagnostic(
                    f"vocabulary.{term}",
                    "PML-E-VOCABULARY-DUPLICATE",
                    f"vocabulary term '{term}' duplicates {source_kind} '{identifier}'",
                )
            )

    forbidden: dict[str, str] = {}
    for definitions in (vocabulary_map, actors_map, concepts_map):
        for canonical, definition in definitions.items():
            if not isinstance(definition, dict):
                continue
            for synonym in definition.get("forbidden_synonyms", []):
                if not isinstance(synonym, str):
                    continue
                forbidden[synonym.casefold()] = canonical

    normative_fields = {"statement"}
    for parts, value in _walk(document):
        if isinstance(value, (date, datetime)):
            diagnostics.append(
                Diagnostic(_path(parts), "implicit-type", "dates must be quoted strings")
            )
        if not isinstance(value, str):
            continue
        lowered = value.casefold()
        defining_forbidden_synonym = len(parts) > 1 and parts[-2] == "forbidden_synonyms"
        if not defining_forbidden_synonym:
            for synonym, canonical in forbidden.items():
                if re.search(rf"\b{re.escape(synonym)}\b", lowered):
                    diagnostics.append(
                        Diagnostic(
                            _path(parts),
                            "forbidden-term",
                            f"use canonical term '{canonical}' instead of '{synonym}'",
                        )
                    )
        transition_text = _is_transition_text(parts)
        is_normative = (bool(parts) and parts[-1] in normative_fields) or transition_text
        if is_normative:
            if not transition_text and not NORMATIVE_MARKER.search(value):
                diagnostics.append(
                    Diagnostic(
                        _path(parts),
                        "non-normative",
                        "normative statements must contain MUST or MUST NOT",
                    )
                )
            for word in AMBIGUOUS_WORDS:
                if re.search(rf"\b{re.escape(word)}\b", lowered):
                    diagnostics.append(
                        Diagnostic(
                            _path(parts),
                            "ambiguous-language",
                            f"replace ambiguous term '{word}' with an observable obligation",
                        )
                    )
            if transition_text and TRANSITION_IMPLEMENTATION_DETAIL.search(value):
                diagnostics.append(
                    Diagnostic(
                        _path(parts),
                        "implementation-detail",
                        "behavior transitions must describe observable product semantics, not implementation details",
                    )
                )

    diagnostics.extend(_surface_diagnostics(document))
    diagnostics.extend(_condition_diagnostics(document))
    diagnostics.extend(_transition_diagnostics(document))

    if resolution is None:
        resolution = resolve_references(document)
    for step in resolution.steps:
        diagnostics.extend(step.diagnostics)
        if step.kind == "signal":
            meaning = step.definition.get("meaning")
            if isinstance(meaning, str) and TRANSITION_IMPLEMENTATION_DETAIL.search(meaning):
                diagnostics.append(
                    Diagnostic(
                        f"{step.path}.meaning",
                        "implementation-detail",
                        "signal meanings must describe product occurrences, not implementation details",
                    )
                )
        elif step.kind == "architecture":
            for field in ("selection", "rationale"):
                value = step.definition.get(field, "")
                if isinstance(value, str) and ARCHITECTURE_IMPLEMENTATION_DETAIL.search(value):
                    diagnostics.append(Diagnostic(f"{step.path}.{field}", "implementation-detail", "architecture must not name implementation files, functions, classes, tables, endpoints, configuration syntax, or topology"))
            constraints = step.definition.get("constraints", {})
            if not isinstance(constraints, dict):
                continue
            for constraint_id, constraint in constraints.items():
                if not isinstance(constraint, dict):
                    continue
                statement = constraint.get("statement", "")
                if isinstance(statement, str) and ARCHITECTURE_IMPLEMENTATION_DETAIL.search(statement):
                    diagnostics.append(Diagnostic(f"{step.path}.constraints.{constraint_id}.statement", "implementation-detail", "architecture must not name implementation files, functions, classes, tables, endpoints, configuration syntax, or topology"))
    return diagnostics


def _merge(base: Any, extra: Any, source: str, parts: tuple[Any, ...], diagnostics: list[Diagnostic]) -> Any:
    if base is None:
        return extra
    if isinstance(base, dict) and isinstance(extra, dict):
        for key, value in extra.items():
            base[key] = _merge(base.get(key), value, source, parts + (key,), diagnostics)
        return base
    diagnostics.append(
        Diagnostic(_path(parts), "conflict", f"'{_path(parts)}' is already defined; duplicate in {source}")
    )
    return base


def _load(path: Path) -> tuple[dict[str, Any] | None, list[Diagnostic]]:
    try:
        document = yaml.load(path.read_text(), Loader=UniqueKeyLoader)
    except _LoadingError as exc:
        location = f"{path}:{exc.mark.line + 1}:{exc.mark.column + 1}"
        return None, [Diagnostic(location, exc.code, exc.message)]
    except (OSError, yaml.YAMLError) as exc:
        return None, [Diagnostic(str(path), "yaml", str(exc))]
    if not isinstance(document, dict):
        return None, [Diagnostic(str(path), "structure", "a PML document must be a mapping")]
    return document, []


SUFFIX = ".pml.yaml"
INDEX = "index"


def _mounted(root: Path, source: Path, fragment: dict[str, Any]) -> Any:
    parts = source.parent.relative_to(root).parts
    name = source.name[: -len(SUFFIX)]
    if name != INDEX:
        parts = parts + (name,)
    mounted: Any = fragment
    for key in reversed(parts):
        mounted = {key: mounted}
    return mounted


def load_document(path: Path) -> tuple[dict[str, Any] | None, list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    document: dict[str, Any] = {}
    if path.is_dir():
        sources = sorted(path.rglob(f"*{SUFFIX}"))
        if not sources:
            return None, [Diagnostic(str(path), "structure", f"no *{SUFFIX} files found")]
        fragments: list[tuple[Path, dict[str, Any]]] = []
        for source in sources:
            fragment, load_diagnostics = _load(source)
            diagnostics.extend(load_diagnostics)
            if fragment is not None:
                fragments.append((source, fragment))
        # These loading preconditions must reject the complete modular input
        # before any accepted fragment can affect the merged document.  Keep
        # established diagnostics from other loader failures unchanged.
        if any(
            diagnostic.code in {"non-string-key", "invalid-unicode-scalar"}
            for diagnostic in diagnostics
        ):
            return None, diagnostics
        for source, fragment in fragments:
            _merge(document, _mounted(path, source, fragment), str(source), (), diagnostics)
    else:
        fragment, load_diagnostics = _load(path)
        diagnostics.extend(load_diagnostics)
        if fragment is not None:
            document = fragment
    if diagnostics:
        return None, diagnostics

    return document, []


def validate_file(path: Path) -> list[Diagnostic]:
    document, diagnostics = load_document(path)
    if document is None:
        return diagnostics

    return list(validate_document(document).diagnostics)


def validate_document(document: dict[str, Any]) -> ResolvedDefinition:
    """Validate and resolve one loaded snapshot, compiling without errors."""

    diagnostics: list[Diagnostic] = []
    validator = Draft202012Validator(_schema())
    for error in sorted(
        validator.iter_errors(document), key=lambda item: list(item.absolute_path)
    ):
        diagnostics.append(
            Diagnostic(_path(error.absolute_path), "schema", error.message)
        )

    resolver = ReferenceResolver(document)
    resolution = resolver.resolve()
    diagnostics.extend(_semantic_diagnostics(document, resolution))
    diagnostics.extend(_cardinality_warnings(document))
    if any(diagnostic.severity == "error" for diagnostic in diagnostics):
        return replace(
            resolution,
            diagnostics=tuple(diagnostics),
            compiled_model=None,
        )

    from pml.model_builder import _build_compiled_model

    compiled_model = _build_compiled_model(resolver.document, resolver, resolution)
    diagnostics.extend(_rule_scope_warnings(compiled_model))
    diagnostics.extend(signal_coupling_warnings(compiled_model))
    diagnostics.extend(_state_transition_warnings(compiled_model))
    return replace(
        resolution,
        diagnostics=tuple(diagnostics),
        compiled_model=compiled_model,
    )
