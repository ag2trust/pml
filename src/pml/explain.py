"""Read-only query and presentation helpers for compiled PML models.

The helpers in this module consume only a complete compiled model.  They do
not load definitions, resolve references, or access product-local state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import textwrap
from types import MappingProxyType
from typing import Any

from pml.coupling import feature_coupling


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

    model: Mapping[str, Any]
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
        and model.get("format_version") == 5
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
        model=model,
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


def explain_compiled_model(
    model: Mapping[str, Any], canonical_id: str, *, raw: bool = False
) -> ExplainResult:
    """Render every matching record from a supported compiled model.

    The format check deliberately precedes building any index or reading record
    collections, as required of every compiled-model consumer.

    The default is the stable, concise human summary.  ``raw`` deliberately
    retains the original complete record rendering for diagnosis and snapshots.
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

    if raw:
        rendered = (
            _render_raw_record(category, record, indexes) for category, record in matches
        )
    else:
        rendered = _render_summary_matches(matches, indexes)
    return ExplainResult(output="\n\n".join(rendered) + "\n")


def _render_summary_matches(
    matches: Sequence[tuple[str, Record]], indexes: CompiledModelIndexes
) -> list[str]:
    """Render concise summaries without duplicating a use-case obligation.

    A use case and its stable obligation deliberately share one canonical ID.
    The summary renders the user-facing use-case record once, including its
    obligation path and surfaces, while raw mode preserves both compiled
    records exactly as before.
    """

    matched_categories = {category for category, _ in matches}
    return [
        _render_summary_record(category, record, indexes)
        for category, record in matches
        if not (category == "obligations" and record["kind"] == "use_case" and "use_cases" in matched_categories)
    ]


def _render_raw_record(
    category: str, record: Record, indexes: CompiledModelIndexes
) -> str:
    label = next(item.label for item in _REQUESTABLE_CATEGORIES if item.name == category)
    authored, structural, inverse = _record_fields(category, record, indexes)
    sections = (
        [label]
        + _render_section("Authored", authored)
        + _render_section("Derived identity/structural", structural)
        + _render_section("Derived inverse links", inverse)
    )
    if category == "features":
        sections += _render_section(
            "Derived coupling", list(feature_coupling(indexes.model, record["path"]).items())
        )
    return "\n".join(sections)


_SUMMARY_WIDTH = 100


def _render_summary_record(
    category: str, record: Record, indexes: CompiledModelIndexes
) -> str:
    """Render the fixed human-facing summary for one requestable record."""

    if category == "project":
        return _render_scope_summary("Project", record, record["id"], "domains", indexes)
    if category == "vocabulary":
        return _render_term_summary(record)
    if category == "actors":
        return _render_meaning_summary("Actor", record, record["id"])
    if category == "concepts":
        return _render_concept_summary(record, indexes)
    if category == "architecture":
        return _render_architecture_summary(record, indexes)
    if category == "domains":
        return _render_scope_summary("Domain", record, record["path"], "features", indexes)
    if category == "features":
        return _render_feature_summary(record, indexes)
    if category == "behaviors":
        return _render_behavior_summary(record, indexes)
    if category == "use_cases":
        return _render_use_case_summary(record, indexes)
    if category == "signals":
        return _render_signal_summary(record)
    if category == "obligations":
        return _render_obligation_summary(record)
    raise AssertionError(f"unknown compiled record category {category!r}")


def _render_scope_summary(
    label: str,
    record: Record,
    identity: str,
    child_field: str,
    indexes: CompiledModelIndexes,
) -> str:
    lines = [f"{label}: {identity}"]
    lines.extend(_summary_line("  ", "Purpose", record["purpose"]))
    lines.append(f"  {child_field.title()}:")
    children = record[child_field]
    if not children:
        lines.append("    none")
    else:
        category = "domains" if child_field == "domains" else "features"
        for child_path in children:
            child = indexes.categories[category][child_path]
            behavior_count = _child_behavior_count(child, category, indexes)
            rule_count = _descendant_rule_count(child["path"], indexes)
            lines.extend(
                _summary_value(
                    "    ",
                    f"{child['id']}: {behavior_count} behaviors, {rule_count} rules",
                )
            )
    return "\n".join(lines)


def _child_behavior_count(
    record: Record, category: str, indexes: CompiledModelIndexes
) -> int:
    if category == "features":
        return len(record["behaviors"])
    return sum(
        len(feature["behaviors"])
        for feature in indexes.categories["features"].values()
        if feature["domain"] == record["path"]
    )


def _descendant_rule_count(scope: str, indexes: CompiledModelIndexes) -> int:
    return sum(
        obligation["kind"] == "rule"
        and (obligation["node"] == scope or obligation["node"].startswith(f"{scope}."))
        for obligation in indexes.categories["obligations"].values()
    )


def _render_term_summary(record: Record) -> str:
    lines = [f"Vocabulary term: {record['term']}"]
    lines.extend(_summary_line("  ", "Meaning", record["meaning"]))
    lines.extend(_summary_entries("  ", "Forbidden synonyms", record.get("forbidden_synonyms", ())))
    return "\n".join(lines)


def _render_meaning_summary(label: str, record: Record, identity: str) -> str:
    lines = [f"{label}: {identity}"]
    lines.extend(_summary_line("  ", "Meaning", record["meaning"]))
    return "\n".join(lines)


def _render_concept_summary(record: Record, indexes: CompiledModelIndexes) -> str:
    lines = [f"Concept: {record['id']}"]
    lines.extend(_summary_line("  ", "Meaning", record["meaning"]))
    lines.extend(_summary_entries("  ", "States", record.get("states", ())))
    required_by = _required_state_entries(record, indexes)
    if required_by:
        lines.extend(_summary_entries("  ", "Required by", required_by))
    return "\n".join(lines)


def _required_state_entries(record: Record, indexes: CompiledModelIndexes) -> list[str]:
    entries: list[str] = []
    for behavior_path in record.get("required_by", ()):
        behavior = indexes.categories["behaviors"].get(behavior_path)
        if behavior is None:
            continue
        conditions = behavior.get("conditions")
        if not isinstance(conditions, Mapping):
            continue
        for condition in conditions.get("statements", ()):
            if isinstance(condition, Mapping) and condition.get("concept") == record["id"]:
                entries.append(f"{behavior_path}: {condition['state']}")
    return entries


def _render_architecture_summary(record: Record, indexes: CompiledModelIndexes) -> str:
    lines = [f"Architecture decision: {record['path']}"]
    lines.extend(_summary_line("  ", "Category", record["category"]))
    lines.extend(_summary_line("  ", "Selection", record["selection"]))
    lines.extend(_summary_line("  ", "Rationale", record["rationale"]))
    constraints = [
        obligation
        for obligation in indexes.obligations_for_node(record["path"])
        if obligation["kind"] == "architecture_constraint"
    ]
    lines.extend(
        _summary_entries(
            "  ",
            "Constraints",
            [
                f"{_tail_after(obligation['id'], '.constraints.')}: "
                f"{obligation['definition']['statement']}"
                for obligation in constraints
            ],
        )
    )
    return "\n".join(lines)


def _render_feature_summary(record: Record, indexes: CompiledModelIndexes) -> str:
    lines = [f"Feature: {record['path']}"]
    lines.extend(_summary_line("  ", "Purpose", record["purpose"]))
    lines.extend(_feature_behavior_table(record, indexes))
    lines.extend(
        _summary_entries(
            "  ",
            "Rules",
            _rule_entries(record.get("rule_obligations", ()), indexes),
        )
    )
    lines.extend(
        _summary_entries(
            "  ",
            "Use cases",
            _use_case_entries(record.get("use_cases", ()), indexes),
        )
    )
    lines.extend(_summary_entries("  ", "Related to", _relationship_entries(record, indexes)))
    lines.append(_feature_coupling_line(record, indexes))
    return "\n".join(lines)


def _feature_behavior_table(record: Record, indexes: CompiledModelIndexes) -> list[str]:
    lines = ["  Behaviors:", "    ID | Conditions | Trigger | Outcome | Produced | Consumed | Failures"]
    for behavior_path in record["behaviors"]:
        behavior = indexes.categories["behaviors"][behavior_path]
        conditions = behavior.get("conditions")
        condition_count = (
            len(conditions.get("statements", ())) if isinstance(conditions, Mapping) else 0
        )
        values = (
            behavior["id"],
            str(condition_count),
            _trigger_kind(behavior["trigger"]),
            _outcome_kind(behavior["outcome"]),
            _comma_or_none(_produced_signals(behavior)),
            _comma_or_none(_transition_signals(behavior["trigger"])),
            str(len(behavior["failures"])),
        )
        lines.append(f"    {' | '.join(values)}")
    return lines


def _trigger_kind(transition: Record) -> str:
    if transition["kind"] == "one_of":
        return f"one_of:{len(transition['cases'])}"
    case = transition["case"]
    return f"signal:{case['signal']}" if "signal" in case else "statement"


def _outcome_kind(transition: Record) -> str:
    return "direct" if transition["kind"] == "direct" else f"one_of:{len(transition['cases'])}"


def _transition_cases(transition: Record) -> Sequence[Record]:
    return (transition["case"],) if transition["kind"] == "direct" else transition["cases"]


def _transition_signals(transition: Record) -> list[str]:
    return [case["signal"] for case in _transition_cases(transition) if "signal" in case]


def _produced_signals(behavior: Record) -> list[str]:
    """Return every signal emitted by a behavior's outcome or failures."""

    return sorted(
        {
            *_transition_signals(behavior["outcome"]),
            *(failure["signal"] for failure in behavior["failures"] if "signal" in failure),
        }
    )


def _rule_entries(paths: Sequence[str], indexes: CompiledModelIndexes) -> list[str]:
    return [
        f"{_tail_after(path, '.rules.')}: "
        f"{indexes.categories['obligations'][path]['definition']['statement']}"
        for path in paths
    ]


def _use_case_entries(paths: Sequence[str], indexes: CompiledModelIndexes) -> list[str]:
    return [
        f"{use_case['id']}: {use_case['goal']} ({len(use_case['behaviors'])} behaviors)"
        for path in paths
        if (use_case := indexes.categories["use_cases"].get(path)) is not None
    ]


def _feature_coupling_line(record: Record, indexes: CompiledModelIndexes) -> str:
    coupling = feature_coupling(indexes.model, record["path"])
    producer_features = sorted(
        {
            signal["producer_feature"]
            for signal in coupling["signals_consumed"]
            if signal["producer_feature"] != record["path"]
        }
    )
    produced_signal_ids = {signal["id"] for signal in coupling["signals_produced"]}
    behavior_features = {
        behavior["path"]: behavior["feature"] for behavior in indexes.categories["behaviors"].values()
    }
    consumer_features = sorted(
        {
            behavior_features[consumer["behavior"]]
            for signal in indexes.categories["signals"].values()
            if signal["id"] in produced_signal_ids
            for consumer in signal["consumers"]
            if behavior_features[consumer["behavior"]] != record["path"]
        }
    )
    return (
        f"  Coupling: producer features ({len(producer_features)}): "
        f"{_comma_or_none(producer_features)}; consumer features ({len(consumer_features)}): "
        f"{_comma_or_none(consumer_features)}"
    )


def _render_behavior_summary(record: Record, indexes: CompiledModelIndexes) -> str:
    lines = [f"Behavior: {record['path']}"]
    lines.extend(_summary_entries("  ", "Conditions", _condition_entries(record)))
    lines.extend(_summary_entries("  ", "Trigger", _transition_entries("trigger", record["trigger"])))
    lines.extend(_summary_entries("  ", "Outcome", _transition_entries("outcome", record["outcome"])))
    lines.extend(
        _summary_entries(
            "  ",
            "Failures",
            [f"{failure['id']}: {failure['statement']}" for failure in record["failures"]],
        )
    )
    lines.extend(_summary_entries("  ", "Signals produced", _produced_signals(record)))
    lines.extend(_summary_entries("  ", "Signals consumed", _transition_signals(record["trigger"])))
    lines.extend(
        _summary_entries(
            "  ",
            "Obligation paths",
            [obligation["id"] for obligation in indexes.obligations_for_node(record["path"])],
        )
    )
    lines.extend(_summary_entries("  ", "Related to", _relationship_entries(record, indexes)))
    lines.extend(_summary_entries("  ", "Use cases", record.get("use_cases", ())))
    return "\n".join(lines)


def _condition_entries(record: Record) -> list[str]:
    conditions = record.get("conditions")
    if not isinstance(conditions, Mapping):
        return []
    entries = []
    for position, condition in enumerate(conditions.get("statements", ()), start=1):
        if isinstance(condition, Mapping):
            entries.append(f"{condition['concept']}: {condition['state']}")
        else:
            entries.append(f"{position}: {condition}")
    return entries


def _transition_entries(label: str, transition: Record) -> list[str]:
    entries = []
    for case in _transition_cases(transition):
        case_id = label if transition["kind"] == "direct" else case["id"]
        value = case["statement"] if "statement" in case else f"signal {case['signal']}"
        entries.append(f"{case_id}: {value}")
    return entries


def _relationship_entries(record: Record, indexes: CompiledModelIndexes) -> list[str]:
    """Render the canonical relationship union for a feature or behavior."""

    path = record["path"]
    return [
        f"{next(endpoint for endpoint in relationship['endpoints'] if endpoint != path)} "
        f"(source: {relationship['source']})"
        for relationship in indexes.relationships_for_endpoint(path)
    ]


def _authored_related_to(record: Record) -> list[dict[str, str]]:
    """Preserve each authored target while making its source explicit."""

    return [{"target": target, "source": "authored"} for target in record["related_to"]]


def _render_use_case_summary(record: Record, indexes: CompiledModelIndexes) -> str:
    obligation = indexes.categories["obligations"].get(record["obligation"])
    surfaces = obligation.get("surfaces", ()) if obligation is not None else ()
    lines = [f"Use case: {record['path']}"]
    lines.extend(_summary_line("  ", "Goal", record["goal"]))
    lines.extend(_summary_line("  ", "Scope", record["feature"]))
    lines.extend(_summary_line("  ", "Obligation path", record["obligation"]))
    lines.extend(_summary_entries("  ", "Surfaces", surfaces))
    return "\n".join(lines)


def _render_signal_summary(record: Record) -> str:
    lines = [f"Signal: {record['id']}"]
    lines.extend(_summary_line("  ", "Meaning", record["meaning"]))
    lines.extend(_summary_line("  ", "Subject", record.get("subject", "none")))
    lines.extend(_summary_line("  ", "Produced by", record["producer"]["behavior"]))
    lines.extend(
        _summary_entries(
            "  ", "Consumed by", [consumer["behavior"] for consumer in record["consumers"]]
        )
    )
    return "\n".join(lines)


def _render_obligation_summary(record: Record) -> str:
    label = {
        "rule": "Rule",
        "use_case": "Use case obligation",
        "architecture_constraint": "Architecture constraint",
    }.get(record["kind"], "Obligation")
    definition = record["definition"]
    lines = [f"{label}: {record['id']}"]
    if "statement" in definition:
        lines.extend(_summary_line("  ", "Statement", definition["statement"]))
    elif "signal" in definition:
        lines.extend(_summary_line("  ", "Signal", definition["signal"]))
    elif "statements" in definition:
        lines.extend(_summary_entries("  ", "Conditions", _definition_condition_entries(definition)))
    elif "goal" in definition:
        lines.extend(_summary_line("  ", "Goal", definition["goal"]))
    elif "outcomes" in definition:
        lines.extend(_summary_entries("  ", "Outcomes", definition["outcomes"]))
        lines.extend(_summary_entries("  ", "Failures", definition["failures"]))
    elif "alternatives" in definition:
        lines.extend(_summary_entries("  ", "Alternatives", definition["alternatives"]))
    lines.extend(_summary_line("  ", "Scope", record["node"]))
    lines.extend(_summary_line("  ", "Obligation path", record["id"]))
    lines.extend(_summary_entries("  ", "Surfaces", record.get("surfaces", ())))
    return "\n".join(lines)


def _definition_condition_entries(definition: Record) -> list[str]:
    return [
        f"{condition['concept']}: {condition['state']}"
        if isinstance(condition, Mapping)
        else f"{position}: {condition}"
        for position, condition in enumerate(definition["statements"], start=1)
    ]


def _summary_line(indent: str, label: str, value: Any) -> list[str]:
    return _wrap_summary(_plain_text(value), f"{indent}{label}: ")


def _summary_value(indent: str, value: Any) -> list[str]:
    return _wrap_summary(_plain_text(value), indent)


def _summary_entries(indent: str, title: str, entries: Sequence[Any]) -> list[str]:
    lines = [f"{indent}{title}:"]
    if not entries:
        return lines + [f"{indent}  none"]
    for entry in entries:
        lines.extend(_summary_value(f"{indent}  ", entry))
    return lines


def _wrap_summary(value: str, initial_indent: str) -> list[str]:
    return textwrap.wrap(
        value,
        width=_SUMMARY_WIDTH,
        initial_indent=initial_indent,
        subsequent_indent=" " * len(initial_indent),
        break_long_words=True,
        break_on_hyphens=False,
    ) or [initial_indent.rstrip()]


def _plain_text(value: Any) -> str:
    """Keep scalar text readable when authored text contains control characters."""

    text = str(value)
    escapes = {"\b": r"\b", "\t": r"\t", "\n": r"\n", "\f": r"\f", "\r": r"\r"}
    return "".join(
        escapes.get(character, f"\\u{ord(character):04x}" if ord(character) < 32 else character)
        for character in text
    )


def _comma_or_none(values: Sequence[str]) -> str:
    return ", ".join(values) if values else "none"


def _tail_after(value: str, marker: str) -> str:
    return value.rsplit(marker, maxsplit=1)[-1]


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
        return (
            _selected(record, "id", "meaning", "states"),
            [],
            _selected(record, "required_by", "transitions"),
        )
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
        authored = _selected(record, "id", "purpose", "actors", "experience")
        authored.append(("related_to", _authored_related_to(record)))
        authored.extend(_selected(record, "architecture"))
        return (
            authored,
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
        (
            "failures",
            [
                dict(_selected(failure, "statement", "signal", "transitions"))
                for failure in failures
            ],
        )
    )
    structural.append(
        ("failures", [dict(_selected(failure, "id", "obligation")) for failure in failures])
    )
    authored.append(("related_to", _authored_related_to(record)))
    return authored, structural


def _transition_authored(field: str, transition: Record) -> list[tuple[str, Any]]:
    if transition["kind"] == "direct":
        return [
            (
                f"{field}.case",
                dict(_selected(transition["case"], "statement", "signal", "transitions")),
            )
        ]
    return [
        (
            f"{field}.cases",
            [
                dict(_selected(case, "statement", "signal", "transitions"))
                for case in transition["cases"]
            ],
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
        "outcome": ("statement", "signal", "transitions"),
        "failure": ("statement", "signal", "transitions"),
        "rule": ("statement",),
        "use_case": ("actor", "goal", "behaviors"),
        "architecture_constraint": ("statement",),
    }[record["kind"]]
    derived_keys = tuple(key for key in definition if key not in authored_keys)
    return (
        _prefixed(definition, "definition", *authored_keys),
        _selected(record, "id", "node", "kind")
        + _prefixed(definition, "definition", *derived_keys),
        _selected(record, "surfaces"),
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
