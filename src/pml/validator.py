"""Restricted-YAML, structural, reference, and language validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
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


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader rejecting aliases, duplicate keys, and implicit dates."""

    def compose_node(self, parent: Any, index: Any) -> yaml.Node:
        if self.check_event(yaml.AliasEvent):
            event = self.peek_event()
            raise yaml.constructor.ConstructorError(
                None, None, f"aliases are forbidden ({event.anchor})", event.start_mark
            )
        return super().compose_node(parent, index)


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

    normative_fields = {"statement", "must"}
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
    event_ids = set(document.get("events", {}))
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
            for event in feature.get("produces", []) + feature.get("consumes", []):
                if event not in event_ids:
                    diagnostics.append(Diagnostic(prefix, "undefined-reference", f"unknown event '{event}'"))
    node_ids = {node_id for node_id, _ in iter_nodes(document)}
    for node_id, node in iter_nodes(document):
        for dependency in node.get("depends_on", []):
            if dependency not in node_ids:
                diagnostics.append(Diagnostic(f"{node_id}.depends_on", "undefined-reference", f"unknown node '{dependency}'"))
        for reaction_id, reaction in node.get("reactions", {}).items():
            event = reaction.get("when")
            if event not in event_ids:
                diagnostics.append(Diagnostic(f"{node_id}.reactions.{reaction_id}.when", "undefined-reference", f"unknown event '{event}'"))
        for rule_id, rule in node.get("rules", {}).items():
            if rule.get("severity") == "critical":
                required = set(rule.get("verification", {}).get("requires", []))
                if not required.intersection({"deterministic_probe", "human_attestation"}):
                    diagnostics.append(Diagnostic(
                        f"{node_id}.rules.{rule_id}.verification.requires",
                        "evidence-routing",
                        "critical rules require deterministic_probe or human_attestation",
                    ))
    return diagnostics


MAX_COMPONENT_DEPTH = 2


def _component_depth_diagnostics(document: dict[str, Any]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for parts, value in _walk(document):
        depth = sum(1 for part in parts if part == "components")
        if depth > MAX_COMPONENT_DEPTH and parts[-1] == "components" and isinstance(value, dict):
            diagnostics.append(
                Diagnostic(
                    _path(parts),
                    "component-depth",
                    f"component nesting is limited to {MAX_COMPONENT_DEPTH} levels",
                )
            )
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
    diagnostics.extend(_component_depth_diagnostics(document))
    return diagnostics
