"""Restricted-YAML, structural, reference, and language validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import copy
import json
from pathlib import Path
import re
from typing import Any, Iterable

from jsonschema import Draft202012Validator
import yaml

from pml.obligations import iter_nodes


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


def _construct_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    mapping: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise _LoadingError(
                "non-string-key",
                f"mapping key decodes to YAML {_yaml_type_name(key)}",
                key_node.start_mark,
            )
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key: {key}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)
UniqueKeyLoader.add_constructor("tag:yaml.org,2002:str", _construct_string)


@dataclass(frozen=True)
class Diagnostic:
    path: str
    code: str
    message: str

    def format(self) -> str:
        return f"{self.path}: [{self.code}] {self.message}"


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


def _completion_cases(node: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    """Yield authored outcome and failure paths and definitions."""

    outcome = node.get("outcome")
    if not isinstance(outcome, dict):
        outcome = {}
    alternatives = outcome.get("one_of")
    if isinstance(alternatives, dict):
        for alternative_id, definition in alternatives.items():
            if isinstance(definition, dict):
                yield f"outcome.one_of.{alternative_id}", definition
    elif "statement" in outcome:
        yield "outcome", outcome
    failures = node.get("failures", {})
    if isinstance(failures, dict):
        for failure_id, definition in failures.items():
            if isinstance(definition, dict):
                yield f"failures.{failure_id}", definition


def _trigger_cases(node: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
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


def _is_behavior_node(node_id: str) -> bool:
    """Return whether a semantic ID has the canonical behavior path shape."""

    parts = node_id.split(".")
    return (
        len(parts) == 6
        and parts[0] == "domains"
        and parts[2] == "features"
        and parts[4] == "behaviors"
    )


def _semantic_diagnostics(document: dict[str, Any]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    vocabulary = document.get("vocabulary", {})
    vocabulary_map = vocabulary if isinstance(vocabulary, dict) else {}
    forbidden: dict[str, str] = {}
    for canonical, definition in vocabulary_map.items():
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

    actors = document.get("actors", {})
    actor_ids = set(actors) if isinstance(actors, dict) else set()
    concepts = document.get("concepts", {})
    concept_ids = set(concepts) if isinstance(concepts, dict) else set()
    architecture = document.get("architecture", {})
    architecture_map = architecture if isinstance(architecture, dict) else {}
    architecture_ids = set(architecture_map)
    referenced_architecture: set[str] = set()
    node_ids = {node_id for node_id, _ in iter_nodes(document)}
    behavior_ids = {node_id for node_id in node_ids if _is_behavior_node(node_id)}
    signal_definitions: dict[str, str] = {}

    for node_id, node in iter_nodes(document):
        if not _is_behavior_node(node_id):
            continue
        for completion_path, completion in _completion_cases(node):
            signal = completion.get("signal")
            if not isinstance(signal, dict):
                continue
            signal_id = signal.get("id")
            signal_path = f"{node_id}.{completion_path}.signal"
            if isinstance(signal_id, str):
                prior = signal_definitions.get(signal_id)
                if prior is not None:
                    diagnostics.append(
                        Diagnostic(
                            f"{signal_path}.id",
                            "duplicate-signal",
                            f"signal '{signal_id}' is already defined at {prior}",
                        )
                    )
                else:
                    signal_definitions[signal_id] = signal_path
            subject = signal.get("subject")
            if isinstance(subject, str) and subject not in concept_ids:
                diagnostics.append(
                    Diagnostic(
                        f"{signal_path}.subject",
                        "undefined-reference",
                        f"unknown concept '{subject}'",
                    )
                )
            meaning = signal.get("meaning")
            if isinstance(meaning, str) and TRANSITION_IMPLEMENTATION_DETAIL.search(meaning):
                diagnostics.append(
                    Diagnostic(
                        f"{signal_path}.meaning",
                        "implementation-detail",
                        "signal meanings must describe product occurrences, not implementation details",
                    )
                )

    signal_ids = set(signal_definitions)
    for domain_id, domain in document.get("domains", {}).items():
        for feature_id, feature in domain.get("features", {}).items():
            prefix = f"domains.{domain_id}.features.{feature_id}"
            for actor in feature.get("actors", []):
                if actor not in actor_ids:
                    diagnostics.append(Diagnostic(f"{prefix}.actors", "undefined-reference", f"unknown actor '{actor}'"))
            for use_case_id, use_case in feature.get("use_cases", {}).items():
                if not isinstance(use_case, dict):
                    continue
                actor = use_case.get("actor")
                if actor and actor not in actor_ids:
                    diagnostics.append(Diagnostic(f"{prefix}.use_cases.{use_case_id}.actor", "undefined-reference", f"unknown actor '{actor}'"))
                referenced_behaviors = use_case.get("behaviors", [])
                if isinstance(referenced_behaviors, list):
                    for behavior in referenced_behaviors:
                        if isinstance(behavior, str) and behavior not in behavior_ids:
                            diagnostics.append(
                                Diagnostic(
                                    f"{prefix}.use_cases.{use_case_id}.behaviors",
                                    "undefined-reference",
                                    f"unknown behavior '{behavior}'",
                                )
                            )
    for node_id, node in iter_nodes(document):
        related_nodes = node.get("related_to", [])
        if isinstance(related_nodes, list):
            for related in related_nodes:
                if not isinstance(related, str):
                    continue
                if related not in node_ids:
                    diagnostics.append(Diagnostic(f"{node_id}.related_to", "undefined-reference", f"unknown node '{related}'"))
                elif related == node_id:
                    diagnostics.append(Diagnostic(f"{node_id}.related_to", "self-reference", "a node cannot relate to itself"))
        if _is_behavior_node(node_id):
            for trigger_path, trigger in _trigger_cases(node):
                signal = trigger.get("signal")
                if isinstance(signal, str) and signal not in signal_ids:
                    diagnostics.append(
                        Diagnostic(
                            f"{node_id}.{trigger_path}.signal",
                            "undefined-reference",
                            f"unknown signal '{signal}'",
                        )
                    )
        node_architecture = node.get("architecture", [])
        if not _is_behavior_node(node_id) and isinstance(node_architecture, list):
            for decision in node_architecture:
                if not isinstance(decision, str):
                    continue
                referenced_architecture.add(decision)
                if decision not in architecture_ids:
                    diagnostics.append(Diagnostic(f"{node_id}.architecture", "undefined-reference", f"unknown architecture decision '{decision}'"))
    for decision_id, decision in architecture_map.items():
        if not isinstance(decision, dict):
            continue
        prefix = f"architecture.{decision_id}"
        if decision_id not in referenced_architecture:
            diagnostics.append(Diagnostic(prefix, "unreferenced-architecture", "architecture decision is not referenced by a feature"))
        for field in ("selection", "rationale"):
            value = decision.get(field, "")
            if isinstance(value, str) and ARCHITECTURE_IMPLEMENTATION_DETAIL.search(value):
                diagnostics.append(Diagnostic(f"{prefix}.{field}", "implementation-detail", "architecture must not name implementation files, functions, classes, tables, endpoints, configuration syntax, or topology"))
        constraints = decision.get("constraints", {})
        if not isinstance(constraints, dict):
            continue
        for constraint_id, constraint in constraints.items():
            if not isinstance(constraint, dict):
                continue
            statement = constraint.get("statement", "")
            if isinstance(statement, str) and ARCHITECTURE_IMPLEMENTATION_DETAIL.search(statement):
                diagnostics.append(Diagnostic(f"{prefix}.constraints.{constraint_id}.statement", "implementation-detail", "architecture must not name implementation files, functions, classes, tables, endpoints, configuration syntax, or topology"))
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

    validator = Draft202012Validator(_schema())
    for error in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path)):
        diagnostics.append(Diagnostic(_path(error.absolute_path), "schema", error.message))
    diagnostics.extend(_semantic_diagnostics(document))
    return diagnostics
