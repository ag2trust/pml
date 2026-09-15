"""Compatibility helpers for stable obligations and verification bindings."""

from __future__ import annotations

from typing import Any

from pml.diagnostics import Diagnostic
from pml.resolver import (
    OBLIGATION_SECTIONS,
    Obligation,
    enumerate_architecture_obligations,
    enumerate_obligations,
    iter_architecture,
    iter_nodes,
)


# Deterministic probes can exercise an individual observable obligation, but they
# cannot establish a behavior's exclusive completion or a use case's broader goal.
# Keep this classification shared by probe and bindings validation.
PROBE_ELIGIBILITY = {
    "rules": "yes",
    "trigger": "yes",
    "outcome": "yes",
    "failures": "yes",
    "conditions": "partial",
    "completion": "no",
    "use_cases": "no",
    "constraints": "yes",
}
PROBE_INELIGIBLE_CODE = "PML-E-PROBE-INELIGIBLE"
PROBE_ELIGIBILITY_TABLE = "docs/verification.md#deterministic-probe-eligibility"


def probe_eligibility(obligation: Obligation) -> str:
    """Return the deterministic-probe eligibility for an obligation kind."""

    return PROBE_ELIGIBILITY[obligation.section]


def probe_ineligibility_diagnostic(path: str, obligation: Obligation) -> Diagnostic:
    """Explain why a deterministic probe cannot cover ``obligation``."""

    return Diagnostic(
        path,
        PROBE_INELIGIBLE_CODE,
        f"deterministic probes cannot verify {obligation.section} obligations; "
        f"see {PROBE_ELIGIBILITY_TABLE}",
    )


def verification_coverage(plan: dict[str, Any]) -> dict[str, float]:
    """Return approved coverage by evidence method."""

    return {
        "deterministic_probe": sum(plan.get("probes", {}).values()),
        "agent_judgment": float(plan.get("agent_judgment", 0)),
        "human_attestation": float(plan.get("human_attestation", 0)),
    }


def required_methods(plan: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        method for method, coverage in verification_coverage(plan).items() if coverage
    )


def verification_plan(
    bindings: dict[str, Any], obligation: Obligation
) -> dict[str, Any]:
    if obligation.node_id.startswith("architecture."):
        decision_id = obligation.node_id.removeprefix("architecture.")
        return (
            bindings.get("architecture", {})
            .get(decision_id, {})
            .get("verification", {})
            .get(obligation.id, {})
        )
    return (
        bindings.get("bindings", {})
        .get(obligation.node_id, {})
        .get("verification", {})
        .get(obligation.id, {})
    )
