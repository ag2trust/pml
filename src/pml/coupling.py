"""Derived signal coupling views and advisory diagnostics."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pml.diagnostics import Diagnostic


# These advisory thresholds are intentionally shared by validation and explain.
MAX_DISTINCT_PRODUCER_FEATURES = 3
MAX_DISTINCT_CONSUMER_FEATURES = 5


def feature_coupling(
    model: Mapping[str, Any], feature_path: str
) -> dict[str, Any]:
    """Return the deterministic signal coupling view for one compiled feature."""

    behavior_features = _behavior_features(model)
    produced: list[dict[str, str]] = []
    consumed: list[dict[str, str]] = []

    for signal in sorted(model["signals"], key=lambda item: item["id"]):
        producer_behavior = signal["producer"]["behavior"]
        producer_feature = behavior_features[producer_behavior]
        if producer_feature == feature_path:
            produced.append(
                {"id": signal["id"], "producer_behavior": producer_behavior}
            )
        if any(
            behavior_features[consumer["behavior"]] == feature_path
            for consumer in signal["consumers"]
        ):
            consumed.append(
                {"id": signal["id"], "producer_feature": producer_feature}
            )

    producer_features = {
        signal["producer_feature"]
        for signal in consumed
        if signal["producer_feature"] != feature_path
    }
    return {
        "signals_produced": produced,
        "signals_consumed": consumed,
        "distinct_producer_feature_count": len(producer_features),
    }


def signal_coupling_warnings(model: Mapping[str, Any]) -> list[Diagnostic]:
    """Return deterministic coupling warnings derived solely from a compiled model."""

    warnings: list[Diagnostic] = []
    behavior_features = _behavior_features(model)

    for feature in sorted(model["features"], key=lambda item: item["path"]):
        coupling = feature_coupling(model, feature["path"])
        if coupling["distinct_producer_feature_count"] > MAX_DISTINCT_PRODUCER_FEATURES:
            warnings.append(
                Diagnostic(
                    feature["path"],
                    "PML-W-SIGNAL-FAN-IN",
                    "features should consume signals from no more than "
                    f"{MAX_DISTINCT_PRODUCER_FEATURES} distinct other features",
                    severity="warning",
                )
            )

    for signal in sorted(model["signals"], key=lambda item: item["id"]):
        consumer_features = {
            behavior_features[consumer["behavior"]]
            for consumer in signal["consumers"]
        }
        if len(consumer_features) > MAX_DISTINCT_CONSUMER_FEATURES:
            warnings.append(
                Diagnostic(
                    signal["producer"]["completion"],
                    "PML-W-SIGNAL-FAN-OUT",
                    "signals should be consumed by no more than "
                    f"{MAX_DISTINCT_CONSUMER_FEATURES} distinct features",
                    severity="warning",
                )
            )

    return sorted(warnings, key=lambda diagnostic: (diagnostic.path, diagnostic.code))


def _behavior_features(model: Mapping[str, Any]) -> dict[str, str]:
    """Index the compiled behavior-to-feature ownership records."""

    return {
        behavior["path"]: behavior["feature"]
        for behavior in model["behaviors"]
    }
