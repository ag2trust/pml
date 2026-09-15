"""Restricted-YAML, structural, reference, and language validation."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
import copy
import json
from pathlib import Path
import re
from typing import Any, Iterable

from jsonschema import Draft202012Validator
import yaml

from pml.compiled_model import CompiledModel
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


def _semantic_diagnostics(
    document: dict[str, Any],
    resolution: ResolvedDefinition | None = None,
) -> list[Diagnostic]:
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
    return replace(
        resolution,
        diagnostics=tuple(diagnostics),
        compiled_model=compiled_model,
    )
