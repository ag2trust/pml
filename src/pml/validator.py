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


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader rejecting aliases, duplicate keys, and implicit dates."""

    def compose_node(self, parent: Any, index: Any) -> yaml.Node:
        if self.check_event(yaml.AliasEvent):
            event = self.peek_event()
            raise yaml.constructor.ConstructorError(
                None, None, f"aliases are forbidden ({event.anchor})", event.start_mark
            )
        return super().compose_node(parent, index)


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


def _construct_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
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


def _semantic_diagnostics(document: dict[str, Any]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    vocabulary = document.get("vocabulary", {})
    forbidden: dict[str, str] = {}
    for canonical, definition in vocabulary.items():
        for synonym in definition.get("forbidden_synonyms", []):
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
        is_normative = bool(parts) and (
            parts[-1] in normative_fields
        )
        if is_normative:
            if not NORMATIVE_MARKER.search(value):
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

    actor_ids = set(document.get("actors", {}))
    signal_ids = set(document.get("signals", {}))
    architecture_ids = set(document.get("architecture", {}))
    referenced_architecture: set[str] = set()
    for domain_id, domain in document.get("domains", {}).items():
        for feature_id, feature in domain.get("features", {}).items():
            prefix = f"domains.{domain_id}.features.{feature_id}"
            for actor in feature.get("actors", []):
                if actor not in actor_ids:
                    diagnostics.append(Diagnostic(f"{prefix}.actors", "undefined-reference", f"unknown actor '{actor}'"))
            for use_case_id, use_case in feature.get("use_cases", {}).items():
                actor = use_case.get("actor")
                if actor and actor not in actor_ids:
                    diagnostics.append(Diagnostic(f"{prefix}.use_cases.{use_case_id}.actor", "undefined-reference", f"unknown actor '{actor}'"))
    node_ids = {node_id for node_id, _ in iter_nodes(document)}
    for node_id, node in iter_nodes(document):
        for related in node.get("related_to", []):
            if related not in node_ids:
                diagnostics.append(Diagnostic(f"{node_id}.related_to", "undefined-reference", f"unknown node '{related}'"))
            elif related == node_id:
                diagnostics.append(Diagnostic(f"{node_id}.related_to", "self-reference", "a node cannot relate to itself"))
        for signal in node.get("emits", []):
            if signal not in signal_ids:
                diagnostics.append(Diagnostic(f"{node_id}.emits", "undefined-reference", f"unknown signal '{signal}'"))
        for decision in node.get("architecture", []):
            referenced_architecture.add(decision)
            if decision not in architecture_ids:
                diagnostics.append(Diagnostic(f"{node_id}.architecture", "undefined-reference", f"unknown architecture decision '{decision}'"))
        for reaction_id, reaction in node.get("reactions", {}).items():
            signal = reaction.get("on")
            if signal not in signal_ids:
                diagnostics.append(Diagnostic(f"{node_id}.reactions.{reaction_id}.on", "undefined-reference", f"unknown signal '{signal}'"))
    for decision_id, decision in document.get("architecture", {}).items():
        prefix = f"architecture.{decision_id}"
        if decision_id not in referenced_architecture:
            diagnostics.append(Diagnostic(prefix, "unreferenced-architecture", "architecture decision is not referenced by a feature or component"))
        for field in ("selection", "rationale"):
            if ARCHITECTURE_IMPLEMENTATION_DETAIL.search(decision.get(field, "")):
                diagnostics.append(Diagnostic(f"{prefix}.{field}", "implementation-detail", "architecture must not name implementation files, functions, classes, tables, endpoints, configuration syntax, or topology"))
        for constraint_id, constraint in decision.get("constraints", {}).items():
            if ARCHITECTURE_IMPLEMENTATION_DETAIL.search(constraint.get("statement", "")):
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
        for source in sources:
            fragment, load_diagnostics = _load(source)
            diagnostics.extend(load_diagnostics)
            if fragment is not None:
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
