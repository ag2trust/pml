"""Ingest typed verification reports into product-local state files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
import yaml

from pml.obligations import enumerate_obligations, iter_nodes, required_methods, verification_plan
from pml.project_state import canonical_hash, input_fingerprint
from pml.validator import Diagnostic, _load, _path


SCHEMA = Path(__file__).resolve().parents[2] / "schema" / "verification-report.schema.json"


def ingest_report(
    report_path: Path,
    repo_root: Path,
    definition: dict[str, Any],
    probes: dict[str, dict[str, Any]],
) -> list[Diagnostic]:
    report, diagnostics = _load(report_path)
    if report is None:
        return diagnostics
    schema = json.loads(SCHEMA.read_text())
    for error in sorted(
        Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).iter_errors(report),
        key=lambda item: list(item.absolute_path),
    ):
        diagnostics.append(Diagnostic(f"{report_path}:{_path(error.absolute_path)}", "schema", error.message))
    if diagnostics:
        return diagnostics

    obligations = {item.id: item for item in enumerate_obligations(definition)}
    nodes = dict(iter_nodes(definition))
    bindings, binding_errors = _load(repo_root / ".pml" / "bindings.yaml")
    diagnostics.extend(binding_errors)
    if bindings is None:
        return diagnostics
    binding_map = bindings.get("bindings", {})

    for index, check in enumerate(report["checks"]):
        target = obligations.get(check["target"])
        location = f"{report_path}:checks[{index}]"
        if target is None:
            diagnostics.append(Diagnostic(f"{location}.target", "undefined-reference", f"unknown obligation '{check['target']}'"))
            continue
        if check["method"] not in required_methods(verification_plan(bindings, target)):
            diagnostics.append(Diagnostic(f"{location}.method", "unexpected-evidence", f"'{check['method']}' is not required by the approved obligation"))
        if check["method"] == "deterministic_probe":
            probe = probes.get(check["probe"])
            if probe is None:
                diagnostics.append(Diagnostic(f"{location}.probe", "undefined-reference", f"unknown approved probe '{check['probe']}'"))
            elif probe["verifies"] != check["target"]:
                diagnostics.append(Diagnostic(f"{location}.probe", "probe-target", "approved probe verifies a different obligation"))
    if diagnostics:
        return diagnostics

    touched_nodes = {obligations[check["target"]].node_id for check in report["checks"]}
    states: dict[str, tuple[Path, dict[str, Any], str]] = {}
    for node_id in touched_nodes:
        node = nodes[node_id]
        paths = binding_map.get(node_id, {}).get("paths", [])
        current_input = input_fingerprint(repo_root, paths)
        state_path = repo_root / ".pml" / "state" / Path(*node_id.split("."))
        state_path = state_path.with_suffix(".state.yaml")
        state, _ = _load(state_path)
        if state is None:
            state = {
                "pml_state": "0.1",
                "node": node_id,
                "obligations": {
                    obligation.id: {"implemented": "unknown", "evidence": {}}
                    for obligation in enumerate_obligations(definition, node_id)
                },
            }
        state["definition_hash"] = canonical_hash(node)
        state["input_fingerprint"] = current_input
        related_nodes = set(node.get("related_to", []))
        related_nodes.update(
            other_id for other_id, other in nodes.items()
            if node_id in other.get("related_to", [])
        )
        related = {}
        for related_id in related_nodes:
            related_paths = binding_map.get(related_id, {}).get("paths", [])
            related[related_id] = input_fingerprint(repo_root, related_paths)
        if related:
            state["related_fingerprints"] = related
        else:
            state.pop("related_fingerprints", None)
        states[node_id] = (state_path, state, current_input)

    for check in report["checks"]:
        obligation = obligations[check["target"]]
        _, state, current_input = states[obligation.node_id]
        evidence = state["obligations"][obligation.id]["evidence"]
        record: dict[str, Any] = {
            "result": check["result"],
            "input_fingerprint": current_input,
            "recorded": report["recorded"],
            "observation": check["observation"],
        }
        if check.get("evidence"):
            record["artifacts"] = check["evidence"]
        if check["method"] == "deterministic_probe":
            probe_id = check["probe"]
            record["probe_fingerprint"] = canonical_hash(probes[probe_id])
            evidence.setdefault("deterministic_probe", {})[probe_id] = record
        elif check["method"] == "agent_judgment":
            record["reproduction"] = check.get("reproduction", [])
            record.pop("artifacts", None)
            evidence["agent_judgment"] = record
        else:
            record["attester"] = check["attester"]
            record.pop("artifacts", None)
            evidence["human_attestation"] = record

    for state_path, state, _ in states.values():
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(yaml.safe_dump(state, sort_keys=False))
    return []
