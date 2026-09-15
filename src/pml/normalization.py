"""Canonical authored-reference normalization for PML definitions."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import re
from typing import Any


_BARE_ID = re.compile(r"^[a-z][a-z0-9_]*$")


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def is_bare_id(value: Any) -> bool:
    """Return whether a value is an authorable bare PML ID."""

    return isinstance(value, str) and _BARE_ID.fullmatch(value) is not None


def _normalize_behavior_references(
    value: Any, feature_path: str
) -> Any:
    """Expand bare behavior IDs in one authored reference list."""

    if not isinstance(value, list):
        return value
    return [
        f"{feature_path}.behaviors.{reference}"
        if is_bare_id(reference)
        else reference
        for reference in value
    ]


def normalize_definition_references(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy with same-feature behavior references fully qualified.

    Only valid PML definition shapes are eligible, so generic callers of the
    canonical JSON encoder (such as review metadata) retain their own content.
    """

    normalized = deepcopy(dict(document))
    if normalized.get("pml") != "0.1-draft":
        return normalized

    for domain_id, domain in _mapping(normalized.get("domains")).items():
        if not isinstance(domain, dict):
            continue
        for feature_id, feature in _mapping(domain.get("features")).items():
            if not isinstance(feature, dict):
                continue
            feature_path = f"domains.{domain_id}.features.{feature_id}"
            if "related_to" in feature:
                feature["related_to"] = _normalize_behavior_references(
                    feature["related_to"], feature_path
                )
            for behavior in _mapping(feature.get("behaviors")).values():
                if isinstance(behavior, dict) and "related_to" in behavior:
                    behavior["related_to"] = _normalize_behavior_references(
                        behavior["related_to"], feature_path
                    )
            for use_case in _mapping(feature.get("use_cases")).values():
                if isinstance(use_case, dict) and "behaviors" in use_case:
                    use_case["behaviors"] = _normalize_behavior_references(
                        use_case["behaviors"], feature_path
                    )
    return normalized
