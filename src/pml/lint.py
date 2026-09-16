"""Deterministic advisory lint for authored PML definitions."""

from __future__ import annotations

import re
from typing import Any, Iterable

from pml.compiled_model import CompiledModel
from pml.diagnostics import Diagnostic


MAX_ADVISORY_RULES = 7
MAX_ADVISORY_BEHAVIORS = 7
RESTATEMENT_SIMILARITY_THRESHOLD = 0.6
RESTATEMENT_CONTAINED_MIN_WORDS = 4
STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "about",
        "above",
        "across",
        "after",
        "against",
        "along",
        "among",
        "are",
        "around",
        "as",
        "at",
        "be",
        "been",
        "being",
        "before",
        "behind",
        "below",
        "beneath",
        "beside",
        "between",
        "beyond",
        "but",
        "by",
        "can",
        "did",
        "do",
        "does",
        "during",
        "except",
        "for",
        "from",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "near",
        "may",
        "must",
        "not",
        "of",
        "off",
        "on",
        "onto",
        "or",
        "out",
        "outside",
        "over",
        "past",
        "shall",
        "should",
        "since",
        "system",
        "that",
        "the",
        "then",
        "these",
        "this",
        "those",
        "to",
        "through",
        "throughout",
        "toward",
        "towards",
        "under",
        "until",
        "up",
        "upon",
        "when",
        "while",
        "with",
        "without",
        "would",
        "within",
    }
)
GENERIC_QUANTIFIERS = frozenset({"all", "any", "each", "every"})

_WORD = re.compile(r"[\w]+")
_GENERIC_QUANTIFIER = re.compile(
    rf"\b(?:{'|'.join(sorted(GENERIC_QUANTIFIERS))})\b", re.IGNORECASE
)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[tuple[str, Any]]:
    return sorted(_mapping(value).items(), key=lambda item: str(item[0]))


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


def _words(value: str) -> list[str]:
    return _WORD.findall(value.casefold().replace("_", " "))


def _normalized_words(value: str) -> frozenset[str]:
    return frozenset(word for word in _words(value) if word not in STOP_WORDS)


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
        if is_rules_map and len(value) > MAX_ADVISORY_RULES:
            warnings.append(
                Diagnostic(
                    _path(parts),
                    "PML-W-RULE-COUNT",
                    f"rules maps should contain no more than {MAX_ADVISORY_RULES} rules",
                    severity="warning",
                )
            )
        if (
            len(parts) == 5
            and parts[0] == "domains"
            and parts[2] == "features"
            and parts[4] == "behaviors"
            and len(value) > MAX_ADVISORY_BEHAVIORS
        ):
            warnings.append(
                Diagnostic(
                    _path(parts),
                    "PML-W-BEHAVIOR-COUNT",
                    f"features should contain no more than {MAX_ADVISORY_BEHAVIORS} behaviors",
                    severity="warning",
                )
            )
    return warnings


def _rule_statements(document: dict[str, Any]) -> Iterable[tuple[str, str]]:
    """Yield every language rule statement in path order."""

    def statements(rules: Any, rules_path: str) -> Iterable[tuple[str, str]]:
        for rule_id, rule in _items(rules):
            statement = _mapping(rule).get("statement")
            if isinstance(statement, str):
                yield f"{rules_path}.{rule_id}.statement", statement

    yield from statements(document.get("rules"), "rules")
    for domain_id, domain in _items(document.get("domains")):
        domain_map = _mapping(domain)
        domain_path = f"domains.{domain_id}"
        yield from statements(domain_map.get("rules"), f"{domain_path}.rules")
        for feature_id, feature in _items(domain_map.get("features")):
            feature_map = _mapping(feature)
            feature_path = f"{domain_path}.features.{feature_id}"
            yield from statements(feature_map.get("rules"), f"{feature_path}.rules")
            for behavior_id, behavior in _items(feature_map.get("behaviors")):
                behavior_path = f"{feature_path}.behaviors.{behavior_id}"
                yield from statements(
                    _mapping(behavior).get("rules"), f"{behavior_path}.rules"
                )


def _transition_statements(
    transition: Any, transition_path: str
) -> Iterable[tuple[str, str]]:
    transition_map = _mapping(transition)
    statement = transition_map.get("statement")
    if isinstance(statement, str):
        yield f"{transition_path}.statement", statement
    for alternative_id, alternative in _items(transition_map.get("one_of")):
        statement = _mapping(alternative).get("statement")
        if isinstance(statement, str):
            yield f"{transition_path}.one_of.{alternative_id}.statement", statement


def _feature_statements(
    feature: dict[str, Any], feature_path: str
) -> list[tuple[str, str]]:
    """Return behavior and surface text which a feature rule may restate."""

    statements: list[tuple[str, str]] = []
    for behavior_id, behavior in _items(feature.get("behaviors")):
        behavior_map = _mapping(behavior)
        behavior_path = f"{feature_path}.behaviors.{behavior_id}"
        conditions = behavior_map.get("conditions")
        if isinstance(conditions, list):
            for index, condition in enumerate(conditions):
                if isinstance(condition, str):
                    statements.append((f"{behavior_path}.conditions[{index}]", condition))
        statements.extend(
            _transition_statements(
                behavior_map.get("trigger"), f"{behavior_path}.trigger"
            )
        )
        statements.extend(
            _transition_statements(
                behavior_map.get("outcome"), f"{behavior_path}.outcome"
            )
        )
        for failure_id, failure in _items(behavior_map.get("failures")):
            statement = _mapping(failure).get("statement")
            if isinstance(statement, str):
                statements.append(
                    (f"{behavior_path}.failures.{failure_id}.statement", statement)
                )

    experience = _mapping(feature.get("experience"))
    for surface_id, surface in _items(experience.get("surfaces")):
        surface_map = _mapping(surface)
        surface_path = f"{feature_path}.experience.surfaces.{surface_id}"
        contains = surface_map.get("contains")
        if isinstance(contains, list):
            for index, item in enumerate(contains):
                if isinstance(item, str):
                    statements.append((f"{surface_path}.contains[{index}]", item))
        for state_id, state in _items(surface_map.get("states")):
            state_path = f"{surface_path}.states.{state_id}"
            contains = _mapping(state).get("contains")
            if isinstance(contains, list):
                for index, item in enumerate(contains):
                    if isinstance(item, str):
                        statements.append((f"{state_path}.contains[{index}]", item))
    return statements


def _best_restatement(rule: str, candidates: Iterable[tuple[str, str]]) -> str | None:
    rule_words = _normalized_words(rule)
    matches: list[tuple[float, str]] = []
    for path, candidate in candidates:
        candidate_words = _normalized_words(candidate)
        if not rule_words or not candidate_words:
            continue
        shared = rule_words & candidate_words
        similarity = len(shared) / len(rule_words | candidate_words)
        smaller = min(len(rule_words), len(candidate_words))
        contained = smaller >= RESTATEMENT_CONTAINED_MIN_WORDS and len(shared) == smaller
        if similarity >= RESTATEMENT_SIMILARITY_THRESHOLD or contained:
            matches.append((similarity, path))
    if not matches:
        return None
    return min(matches, key=lambda match: (-match[0], match[1]))[1]


def _restatement_warnings(document: dict[str, Any]) -> list[Diagnostic]:
    warnings: list[Diagnostic] = []
    for domain_id, domain in _items(document.get("domains")):
        for feature_id, feature in _items(_mapping(domain).get("features")):
            feature_map = _mapping(feature)
            feature_path = f"domains.{domain_id}.features.{feature_id}"
            candidates = _feature_statements(feature_map, feature_path)
            for rule_id, rule in _items(feature_map.get("rules")):
                statement = _mapping(rule).get("statement")
                if not isinstance(statement, str):
                    continue
                matched_path = _best_restatement(statement, candidates)
                if matched_path is not None:
                    warnings.append(
                        Diagnostic(
                            f"{feature_path}.rules.{rule_id}.statement",
                            "PML-W-RULE-RESTATEMENT",
                            f"rule statement restates '{matched_path}'",
                            severity="warning",
                        )
                    )
    return warnings


def _identifiers(document: dict[str, Any]) -> list[str]:
    identifiers = {
        *(_mapping(document.get("actors")).keys()),
        *(_mapping(document.get("concepts")).keys()),
        *(_mapping(document.get("vocabulary")).keys()),
    }
    for _, domain in _items(document.get("domains")):
        for _, feature in _items(_mapping(domain).get("features")):
            identifiers.update(_mapping(_mapping(feature).get("behaviors")).keys())
    return sorted(
        (
            str(identifier)
            for identifier in identifiers
            if str(identifier).replace("_", " ").strip()
        ),
        key=str.casefold,
    )


def _mentions_identifier(statement: str, identifiers: Iterable[str]) -> bool:
    normalized = statement.casefold().replace("_", " ")
    return any(
        _term_pattern(identifier).search(normalized) for identifier in identifiers
    )


def _generic_rule_warnings(document: dict[str, Any]) -> list[Diagnostic]:
    identifiers = _identifiers(document)
    warnings: list[Diagnostic] = []
    for path, statement in _rule_statements(document):
        normalized_statement = statement.replace("_", " ")
        if _GENERIC_QUANTIFIER.search(normalized_statement) and not _mentions_identifier(
            normalized_statement, identifiers
        ):
            warnings.append(
                Diagnostic(
                    path,
                    "PML-W-RULE-GENERIC",
                    "rule uses a generic quantifier without naming an actor, concept, vocabulary key, or behavior",
                    severity="warning",
                )
            )
    return warnings


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

    for transition_name in ("trigger", "outcome"):
        transition = behavior.get(transition_name)
        if not isinstance(transition, dict):
            continue
        cases = (
            transition.get("cases")
            if transition.get("kind") == "one_of"
            else [transition.get("case")]
        )
        if isinstance(cases, list):
            for case in cases:
                if isinstance(case, dict) and isinstance(case.get("statement"), str):
                    yield case["statement"]

    for failure in behavior.get("failures", []):
        if isinstance(failure, dict) and isinstance(failure.get("statement"), str):
            yield failure["statement"]


def rule_scope_warnings(model: CompiledModel) -> list[Diagnostic]:
    """Return deterministic scope advice derived from a compiled model."""

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

    domain_terms: dict[str, set[str]] = {
        domain["path"]: set() for domain in model["domains"]
    }
    for feature in model["features"]:
        domain_terms[feature["domain"]].update(feature_terms[feature["path"]])

    warnings: list[Diagnostic] = []
    for obligation in sorted(model["obligations"], key=lambda item: item["id"]):
        if obligation["kind"] != "rule":
            continue
        node = obligation["node"]
        if node in feature_terms:
            local = feature_terms[node]
            message = (
                "rule mentions no term used in this feature; consider domain or project scope"
            )
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


def lint_document(document: dict[str, Any]) -> list[Diagnostic]:
    """Return all warning-only lint diagnostics in deterministic path order."""

    warnings = [
        *_cardinality_warnings(document),
        *_restatement_warnings(document),
        *_generic_rule_warnings(document),
    ]
    return sorted(warnings, key=lambda diagnostic: (diagnostic.path, diagnostic.code))
