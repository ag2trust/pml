"""Read-only derivation of obligation and node implementation/verification status."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pml.obligations import verification_plan
from pml.resolver import Obligation, enumerate_architecture_obligations, enumerate_obligations, iter_architecture, iter_nodes
from pml.project_state import (
    LockedBindings,
    architecture_state_root_diagnostics,
    product_state_paths_diagnostics,
    canonical_hash,
    input_fingerprint,
    load_locked_bindings,
    load_architecture_state,
    load_product_state,
    state_path_for,
)
from pml.validator import Diagnostic


@dataclass(frozen=True)
class ObligationStatus:
    obligation_id: str
    signal: str
    verified_coverage: float

    @property
    def verification_percent(self) -> float:
        return 100.0 * self.verified_coverage


@dataclass(frozen=True)
class NodeStatus:
    node_id: str
    implementation_percent: float
    verification_percent: float
    obligations: tuple[ObligationStatus, ...]


def _current_evidence(record: dict[str, Any], current_input: str, dependencies_current: bool) -> bool:
    return record.get("input_fingerprint") == current_input and dependencies_current


def _lane_records(method: str, evidence: dict[str, Any]) -> list[dict[str, Any]]:
    value = evidence.get(method)
    if value is None:
        return []
    if method == "deterministic_probe":
        return list(value.values())
    return [value]


def derive_obligation_status(
    obligation: Obligation,
    state: dict[str, Any],
    current_input: str,
    related_current: bool,
    plan: dict[str, Any] | None = None,
) -> ObligationStatus:
    plan = plan or {}
    evidence = state.get("evidence", {})
    verified_coverage = 0.0
    has_prior = False
    current_results: list[str] = []
    methods = {
        "deterministic_probe": plan.get("probes", {}),
        "agent_judgment": plan.get("agent_judgment", 0),
        "human_attestation": plan.get("human_attestation", 0),
    }
    for method, configured in methods.items():
        if not configured:
            continue
        if method == "deterministic_probe":
            probe_evidence = evidence.get(method, {})
            records = [
                probe_evidence[probe_id]
                for probe_id in configured
                if probe_id in probe_evidence
            ]
        else:
            records = _lane_records(method, evidence)
        has_prior = has_prior or bool(records)
        current = [
            record for record in records
            if _current_evidence(record, current_input, related_current)
        ]
        current_results.extend(record["result"] for record in current)
        if method == "deterministic_probe":
            for probe_id, coverage in configured.items():
                record = probe_evidence.get(probe_id)
                if (
                    record
                    and _current_evidence(record, current_input, related_current)
                    and record["result"] == "passed"
                ):
                    verified_coverage += coverage
        elif configured and current and all(record["result"] == "passed" for record in current):
            verified_coverage += configured

    if "failed" in current_results:
        signal = "FAILED"
    elif "blocked" in current_results:
        signal = "BLOCKED"
    elif verified_coverage >= 1.0 - 1e-9:
        signal = "VERIFIED"
    elif verified_coverage:
        signal = "PARTIAL"
    elif has_prior and not current_results:
        signal = "STALE"
    else:
        signal = "UNVERIFIED"
    return ObligationStatus(obligation.id, signal, min(verified_coverage, 1.0))


def product_status(
    repo_root: Path,
    definition: dict[str, Any],
    locked_bindings: LockedBindings | None = None,
    *,
    definition_source: Path | None = None,
    state_diagnostics: list[Diagnostic] | None = None,
) -> list[NodeStatus]:
    if locked_bindings is None:
        locked_bindings, _ = load_locked_bindings(
            repo_root, definition, definition_source
        )
    if locked_bindings is None:
        return []
    state_paths = [
        state_path_for(repo_root, node_id)
        for node_id, _ in iter_nodes(definition)
    ]
    path_errors = product_state_paths_diagnostics(repo_root, state_paths)
    if path_errors:
        if state_diagnostics is not None:
            state_diagnostics.extend(path_errors)
        return []
    bindings = locked_bindings.document
    binding_map = bindings["bindings"]
    nodes = dict(iter_nodes(definition))
    result: list[NodeStatus] = []
    implementation_weight = {"implemented": 1.0, "partial": 0.5, "missing": 0.0, "unknown": 0.0}

    for node_id, node in nodes.items():
        state_path = state_path_for(repo_root, node_id)
        state, errors = load_product_state(repo_root, state_path)
        if state_diagnostics is not None:
            state_diagnostics.extend(errors)
        state = state or {"obligations": {}, "related_fingerprints": {}}
        policy_current = state.get("bindings_digest") == locked_bindings.digest
        paths = binding_map.get(node_id, {}).get("paths", [])
        current_input = input_fingerprint(repo_root, paths)
        related_current = policy_current
        related_nodes = set(node.get("related_to", []))
        related_nodes.update(
            other_id for other_id, other in nodes.items()
            if node_id in other.get("related_to", [])
        )
        for related in related_nodes:
            related_paths = binding_map.get(related, {}).get("paths", [])
            current_related = input_fingerprint(repo_root, related_paths)
            if state.get("related_fingerprints", {}).get(related) != current_related:
                related_current = False

        obligations = list(enumerate_obligations(definition, node_id))
        statuses: list[ObligationStatus] = []
        implemented_total = 0.0
        coverage_total = 0.0
        for obligation in obligations:
            obligation_state = state["obligations"].get(
                obligation.id, {"implemented": "unknown", "evidence": {}}
            )
            implemented_total += implementation_weight[obligation_state["implemented"]]
            status = derive_obligation_status(
                obligation,
                obligation_state,
                current_input,
                related_current,
                verification_plan(bindings, obligation),
            )
            statuses.append(status)
            coverage_total += status.verified_coverage
        result.append(NodeStatus(
            node_id=node_id,
            implementation_percent=(100.0 * implemented_total / len(obligations)) if obligations else 100.0,
            verification_percent=(100.0 * coverage_total / len(obligations)) if obligations else 100.0,
            obligations=tuple(statuses),
        ))
    return result


def architecture_status(
    repo_root: Path,
    definition: dict[str, Any],
    locked_bindings: LockedBindings | None = None,
    *,
    definition_source: Path | None = None,
    state_diagnostics: list[Diagnostic] | None = None,
) -> list[NodeStatus]:
    """Derive architecture conformance separately from product conformance."""

    if locked_bindings is None:
        locked_bindings, _ = load_locked_bindings(
            repo_root, definition, definition_source
        )
    if locked_bindings is None:
        return []
    root_errors = architecture_state_root_diagnostics(repo_root)
    if root_errors:
        if state_diagnostics is not None:
            state_diagnostics.extend(root_errors)
        return []
    bindings = locked_bindings.document
    binding_map = bindings.get("architecture", {})
    result: list[NodeStatus] = []
    implementation_weight = {"implemented": 1.0, "partial": 0.5, "missing": 0.0, "unknown": 0.0}
    for node_id, decision in iter_architecture(definition):
        obligations = list(enumerate_architecture_obligations(definition, node_id))
        if not obligations:
            continue
        decision_id = node_id.removeprefix("architecture.")
        state_path = state_path_for(repo_root, node_id)
        state, errors = load_architecture_state(repo_root, state_path)
        if state is not None and state["node"] != node_id:
            errors.append(Diagnostic(
                f"{state_path}:node",
                "state-path",
                f"state for '{state['node']}' must be at {state_path_for(repo_root, state['node'])}",
            ))
            state = None
        if state_diagnostics is not None:
            state_diagnostics.extend(errors)
        state = state or {"obligations": {}}
        policy_current = (
            state.get("definition_hash") == canonical_hash(decision)
            and state.get("bindings_digest") == locked_bindings.digest
        )
        current_input = input_fingerprint(repo_root, binding_map.get(decision_id, {}).get("paths", []))
        statuses: list[ObligationStatus] = []
        implemented_total = 0.0
        coverage_total = 0.0
        for obligation in obligations:
            obligation_state = state["obligations"].get(obligation.id, {"implemented": "unknown", "evidence": {}})
            implemented_total += implementation_weight[obligation_state["implemented"]]
            status = derive_obligation_status(obligation, obligation_state, current_input, policy_current, verification_plan(bindings, obligation))
            statuses.append(status)
            coverage_total += status.verified_coverage
        result.append(NodeStatus(
            node_id=node_id,
            implementation_percent=(100.0 * implemented_total / len(obligations)) if obligations else 100.0,
            verification_percent=(100.0 * coverage_total / len(obligations)) if obligations else 100.0,
            obligations=tuple(statuses),
        ))
    return result
