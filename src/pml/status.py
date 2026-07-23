"""Read-only derivation of obligation and node implementation/verification status."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pml.obligations import Obligation, enumerate_obligations, iter_nodes
from pml.project_state import input_fingerprint
from pml.validator import _load


@dataclass(frozen=True)
class ObligationStatus:
    obligation_id: str
    signal: str
    satisfied_lanes: int
    required_lanes: int

    @property
    def verification_percent(self) -> float:
        if self.required_lanes == 0:
            return 100.0
        return 100.0 * self.satisfied_lanes / self.required_lanes


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
    dependencies_current: bool,
) -> ObligationStatus:
    required = obligation.required_methods
    evidence = state.get("evidence", {})
    satisfied = 0
    has_prior = False
    current_results: list[str] = []
    for method in required:
        records = _lane_records(method, evidence)
        has_prior = has_prior or bool(records)
        current = [
            record for record in records
            if _current_evidence(record, current_input, dependencies_current)
        ]
        current_results.extend(record["result"] for record in current)
        if current and all(record["result"] == "passed" for record in current):
            satisfied += 1

    if "failed" in current_results:
        signal = "FAILED"
    elif "blocked" in current_results:
        signal = "BLOCKED"
    elif satisfied == len(required):
        signal = "VERIFIED"
    elif satisfied:
        signal = "PARTIAL"
    elif has_prior and not current_results:
        signal = "STALE"
    else:
        signal = "UNVERIFIED"
    return ObligationStatus(obligation.id, signal, satisfied, len(required))


def product_status(repo_root: Path, definition: dict[str, Any]) -> list[NodeStatus]:
    metadata = repo_root / ".pml"
    bindings, _ = _load(metadata / "bindings.yaml")
    binding_map = bindings.get("bindings", {}) if bindings else {}
    nodes = dict(iter_nodes(definition))
    result: list[NodeStatus] = []
    implementation_weight = {"implemented": 1.0, "partial": 0.5, "missing": 0.0, "unknown": 0.0}

    for node_id, node in nodes.items():
        state_path = metadata / "state" / Path(*node_id.split("."))
        state_path = state_path.with_suffix(".state.yaml")
        state, _ = _load(state_path)
        state = state or {"obligations": {}, "dependency_fingerprints": {}}
        paths = binding_map.get(node_id, {}).get("paths", [])
        current_input = input_fingerprint(repo_root, paths)
        dependencies_current = True
        for dependency in node.get("depends_on", []):
            dependency_paths = binding_map.get(dependency, {}).get("paths", [])
            current_dependency = input_fingerprint(repo_root, dependency_paths)
            if state.get("dependency_fingerprints", {}).get(dependency) != current_dependency:
                dependencies_current = False

        obligations = list(enumerate_obligations(definition, node_id))
        statuses: list[ObligationStatus] = []
        implemented_total = 0.0
        lane_total = 0
        lane_satisfied = 0
        for obligation in obligations:
            obligation_state = state["obligations"].get(
                obligation.id, {"implemented": "unknown", "evidence": {}}
            )
            implemented_total += implementation_weight[obligation_state["implemented"]]
            status = derive_obligation_status(
                obligation, obligation_state, current_input, dependencies_current
            )
            statuses.append(status)
            lane_total += status.required_lanes
            lane_satisfied += status.satisfied_lanes
        result.append(NodeStatus(
            node_id=node_id,
            implementation_percent=(100.0 * implemented_total / len(obligations)) if obligations else 100.0,
            verification_percent=(100.0 * lane_satisfied / lane_total) if lane_total else 100.0,
            obligations=tuple(statuses),
        ))
    return result
