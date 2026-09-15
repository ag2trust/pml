"""Read-only query and presentation helpers for compiled PML models.

The helpers in this module consume only a complete compiled model.  They do
not load definitions, resolve references, or access product-local state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from types import MappingProxyType
from typing import Any


Record = Mapping[str, Any]


@dataclass(frozen=True)
class _Category:
    """One single-ID compiled-record category in compiled-model order."""

    name: str
    label: str
    collection: str | None
    identity: str


# Relationships and use-case memberships are intentionally absent: their
# identities are endpoint/member tuples, not a canonical ID accepted by explain.
_REQUESTABLE_CATEGORIES = (
    _Category("project", "Project", None, "project"),
    _Category("vocabulary", "Vocabulary term", "vocabulary", "term"),
    _Category("actors", "Actor", "actors", "id"),
    _Category("concepts", "Concept", "concepts", "id"),
    _Category("architecture", "Architecture decision", "architecture", "path"),
    _Category("domains", "Domain", "domains", "path"),
    _Category("features", "Feature", "features", "path"),
    _Category("behaviors", "Behavior", "behaviors", "path"),
    _Category("use_cases", "Use case", "use_cases", "path"),
    _Category("signals", "Signal", "signals", "id"),
    _Category("obligations", "Obligation", "obligations", "id"),
)


@dataclass(frozen=True)
class CompiledModelIndexes:
    """Pure read-only indexes over one supported compiled model."""

    categories: Mapping[str, Mapping[str, Record]]
    reverse: Mapping[str, tuple[str, ...]]
    obligations_by_node: Mapping[str, tuple[Record, ...]]
    relationships_by_endpoint: Mapping[str, tuple[Record, ...]]
    memberships_by_use_case: Mapping[str, tuple[Record, ...]]
    memberships_by_behavior: Mapping[str, tuple[Record, ...]]
    relationships: tuple[Record, ...]
    use_case_memberships: tuple[Record, ...]

    def matching_records(self, canonical_id: str) -> tuple[tuple[str, Record], ...]:
        """Probe every requestable category for ``canonical_id`` in model order."""

        return tuple(
            (category.name, records[canonical_id])
            for category in _REQUESTABLE_CATEGORIES
            if canonical_id in (records := self.categories[category.name])
        )

    def obligations_for_node(self, canonical_id: str) -> tuple[Record, ...]:
        return self.obligations_by_node.get(canonical_id, ())

    def relationships_for_endpoint(self, canonical_id: str) -> tuple[Record, ...]:
        return self.relationships_by_endpoint.get(canonical_id, ())

    def memberships_for_use_case(self, canonical_id: str) -> tuple[Record, ...]:
        return self.memberships_by_use_case.get(canonical_id, ())

    def memberships_for_behavior(self, canonical_id: str) -> tuple[Record, ...]:
        return self.memberships_by_behavior.get(canonical_id, ())


@dataclass(frozen=True)
class ExplainResult:
    """The entirely in-memory result of explaining one compiled-model ID."""

    output: str | None = None
    diagnostic: str | None = None

    @property
    def exit_code(self) -> int:
        return 0 if self.output is not None else 1


def is_supported_model(model: Mapping[str, Any]) -> bool:
    """Return whether ``model`` is exactly the compiled-model version we read."""

    return (
        model.get("format") == "pml.compiled"
        and type(model.get("format_version")) is int
        and model.get("format_version") == 1
    )


def build_compiled_model_indexes(model: Mapping[str, Any]) -> CompiledModelIndexes:
    """Build reusable read-only lookup views without interpreting authored YAML.

    Callers must pass a supported, complete compiled model.  The command-level
    consumer checks that boundary before calling this helper.
    """

    if not is_supported_model(model):
        raise ValueError("unsupported compiled model")

    category_indexes: dict[str, Mapping[str, Record]] = {}
    reverse: dict[str, list[str]] = {}
    for category in _REQUESTABLE_CATEGORIES:
        source: Sequence[Record]
        if category.collection is None:
            source = (model["project"],)
            records = {category.identity: source[0]}
        else:
            source = model[category.collection]
            records = {record[category.identity]: record for record in source}
        category_indexes[category.name] = MappingProxyType(records)
        for canonical_id in records:
            reverse.setdefault(canonical_id, []).append(category.name)

    obligations_by_node: dict[str, list[Record]] = {}
    for obligation in model["obligations"]:
        obligations_by_node.setdefault(obligation["node"], []).append(obligation)

    relationships_by_endpoint: dict[str, list[Record]] = {}
    for relationship in model["relationships"]:
        for endpoint in relationship["endpoints"]:
            relationships_by_endpoint.setdefault(endpoint, []).append(relationship)

    memberships_by_use_case: dict[str, list[Record]] = {}
    memberships_by_behavior: dict[str, list[Record]] = {}
    for membership in model["use_case_memberships"]:
        memberships_by_use_case.setdefault(membership["use_case"], []).append(membership)
        memberships_by_behavior.setdefault(membership["behavior"], []).append(membership)

    return CompiledModelIndexes(
        categories=MappingProxyType(category_indexes),
        reverse=MappingProxyType(
            {canonical_id: tuple(categories) for canonical_id, categories in reverse.items()}
        ),
        obligations_by_node=MappingProxyType(
            {node: tuple(obligations) for node, obligations in obligations_by_node.items()}
        ),
        relationships_by_endpoint=MappingProxyType(
            {
                endpoint: tuple(relationships)
                for endpoint, relationships in relationships_by_endpoint.items()
            }
        ),
        memberships_by_use_case=MappingProxyType(
            {
                use_case: tuple(memberships)
                for use_case, memberships in memberships_by_use_case.items()
            }
        ),
        memberships_by_behavior=MappingProxyType(
            {
                behavior: tuple(memberships)
                for behavior, memberships in memberships_by_behavior.items()
            }
        ),
        relationships=tuple(model["relationships"]),
        use_case_memberships=tuple(model["use_case_memberships"]),
    )


def explain_compiled_model(model: Mapping[str, Any], canonical_id: str) -> ExplainResult:
    """Render every matching record from a supported compiled model.

    The format check deliberately precedes building any index or reading record
    collections, as required of every compiled-model consumer.
    """

    if not is_supported_model(model):
        return ExplainResult(
            diagnostic=(
                f"[unsupported-model] {model.get('format')}@"
                f"{model.get('format_version')} is not supported"
            )
        )

    indexes = build_compiled_model_indexes(model)
    matches = indexes.matching_records(canonical_id)
    if not matches:
        return ExplainResult(
            diagnostic=f"{canonical_id}: [unknown-id] no compiled record matches this ID"
        )

    return ExplainResult(
        output="\n\n".join(
            _render_record(category, record, indexes) for category, record in matches
        )
        + "\n"
    )


def _render_record(
    category: str, record: Record, indexes: CompiledModelIndexes
) -> str:
    label = next(item.label for item in _REQUESTABLE_CATEGORIES if item.name == category)
    authored, structural, inverse = _record_fields(category, record, indexes)
    return "\n".join(
        [label]
        + _render_section("Authored", authored)
        + _render_section("Derived identity/structural", structural)
        + _render_section("Derived inverse links", inverse)
    )


def _record_fields(
    category: str, record: Record, indexes: CompiledModelIndexes
) -> tuple[list[tuple[str, Any]], list[tuple[str, Any]], list[tuple[str, Any]]]:
    if category == "project":
        return (
            _selected(record, "id", "name", "purpose"),
            [],
            _inverse_with_obligations(record, "project", indexes, "rule_obligations", "domains"),
        )
    if category == "vocabulary":
        return _selected(record, "term", "meaning", "forbidden_synonyms"), [], []
    if category == "actors":
        return _selected(record, "id", "meaning"), [], []
    if category == "concepts":
        return _selected(record, "id", "meaning", "states"), [], []
    if category == "architecture":
        return (
            _selected(record, "id", "category", "selection", "rationale"),
            _selected(record, "path"),
            _inverse_with_obligations(
                record, record["path"], indexes, "constraint_obligations", "referenced_by"
            ),
        )
    if category == "domains":
        return (
            _selected(record, "id", "purpose"),
            _selected(record, "path"),
            _inverse_with_obligations(record, record["path"], indexes, "rule_obligations", "features"),
        )
    if category == "features":
        inverse = _inverse_with_obligations(
            record, record["path"], indexes, "rule_obligations", "use_cases", "behaviors"
        )
        inverse.append(("relationships", indexes.relationships_for_endpoint(record["path"])))
        inverse.append(("use_case_memberships", indexes.memberships_for_behavior(record["path"])))
        return (
            _selected(record, "id", "purpose", "actors", "experience", "related_to", "architecture"),
            _selected(record, "path", "domain"),
            inverse,
        )
    if category == "behaviors":
        authored, structural = _behavior_fields(record)
        inverse = _inverse_with_obligations(
            record, record["path"], indexes, "rule_obligations", "use_cases"
        )
        inverse.append(("relationships", indexes.relationships_for_endpoint(record["path"])))
        inverse.append(("use_case_memberships", indexes.memberships_for_behavior(record["path"])))
        return authored, structural, inverse
    if category == "use_cases":
        inverse = [("use_case_memberships", indexes.memberships_for_use_case(record["path"]))]
        return (
            _selected(record, "id", "actor", "goal", "behaviors"),
            _selected(record, "path", "feature", "obligation"),
            inverse,
        )
    if category == "signals":
        return _selected(record, "id", "meaning", "subject"), [], _selected(record, "producer", "consumers")
    if category == "obligations":
        return _obligation_fields(record)
    raise AssertionError(f"unknown compiled record category {category!r}")


def _behavior_fields(record: Record) -> tuple[list[tuple[str, Any]], list[tuple[str, Any]]]:
    authored = _selected(record, "id")
    structural = _selected(record, "path", "feature")

    conditions = record.get("conditions")
    if isinstance(conditions, Mapping):
        authored.extend(_prefixed(conditions, "conditions", "statements"))
        structural.extend(_prefixed(conditions, "conditions", "obligation"))

    for field in ("trigger", "outcome"):
        transition = record[field]
        authored.extend(_transition_authored(field, transition))
        structural.extend(_transition_structural(field, transition))

    structural.extend(_selected(record, "completion_obligation"))
    failures = record["failures"]
    authored.append(
        ("failures", [dict(_selected(failure, "statement", "signal")) for failure in failures])
    )
    structural.append(
        ("failures", [dict(_selected(failure, "id", "obligation")) for failure in failures])
    )
    authored.extend(_selected(record, "related_to"))
    return authored, structural


def _transition_authored(field: str, transition: Record) -> list[tuple[str, Any]]:
    if transition["kind"] == "direct":
        return [(f"{field}.case", dict(_selected(transition["case"], "statement", "signal")))]
    return [
        (
            f"{field}.cases",
            [dict(_selected(case, "statement", "signal")) for case in transition["cases"]],
        )
    ]


def _transition_structural(field: str, transition: Record) -> list[tuple[str, Any]]:
    fields: list[tuple[str, Any]] = [(f"{field}.kind", transition["kind"])]
    if "exclusivity_obligation" in transition:
        fields.append((f"{field}.exclusivity_obligation", transition["exclusivity_obligation"]))
    if transition["kind"] == "direct":
        fields.extend(
            (f"{field}.case.{key}", value)
            for key, value in _selected(transition["case"], "obligation")
        )
    else:
        fields.append(
            (
                f"{field}.cases",
                [dict(_selected(case, "id", "obligation")) for case in transition["cases"]],
            )
        )
    return fields


def _obligation_fields(
    record: Record,
) -> tuple[list[tuple[str, Any]], list[tuple[str, Any]], list[tuple[str, Any]]]:
    definition = record["definition"]
    authored_keys = {
        "conditions": ("statements",),
        "trigger": ("statement", "signal"),
        "completion": (),
        "outcome_exclusivity": (),
        "outcome": ("statement", "signal"),
        "failure": ("statement", "signal"),
        "rule": ("statement",),
        "use_case": ("actor", "goal", "behaviors"),
        "architecture_constraint": ("statement",),
    }[record["kind"]]
    derived_keys = tuple(key for key in definition if key not in authored_keys)
    return (
        _prefixed(definition, "definition", *authored_keys),
        _selected(record, "id", "node", "kind")
        + _prefixed(definition, "definition", *derived_keys),
        [],
    )


def _inverse_with_obligations(
    record: Record,
    canonical_id: str,
    indexes: CompiledModelIndexes,
    *fields: str,
) -> list[tuple[str, Any]]:
    return _selected(record, *fields) + [
        (
            "stable_obligations",
            [obligation["id"] for obligation in indexes.obligations_for_node(canonical_id)],
        )
    ]


def _selected(record: Mapping[str, Any], *keys: str) -> list[tuple[str, Any]]:
    return [(key, record[key]) for key in keys if key in record]


def _prefixed(record: Mapping[str, Any], prefix: str, *keys: str) -> list[tuple[str, Any]]:
    return [(f"{prefix}.{key}", record[key]) for key in keys if key in record]


def _render_section(title: str, fields: Sequence[tuple[str, Any]]) -> list[str]:
    lines = [f"  {title}:"]
    if not fields:
        return lines + ["    (none)"]
    for key, value in fields:
        lines.extend(_render_field(key, value))
    return lines


def _render_field(key: str, value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        if not value:
            return [f"    {key}: []"]
        return [f"    {key}:"] + [f"      - {_display(item)}" for item in value]
    return [f"    {key}: {_display(value)}"]


def _display(value: Any) -> str:
    """Display exact model values without summarizing authored text."""

    return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))
