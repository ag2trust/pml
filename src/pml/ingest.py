"""Ingest typed verification reports into product-local state files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
import yaml

from pml.formats import FORMAT_CHECKER
from pml.obligations import enumerate_architecture_obligations, enumerate_obligations, iter_architecture, iter_nodes, required_methods, verification_plan
from pml.project_state import (
    LockedBindings,
    MAX_STATE_FILE_BYTES,
    architecture_state_root_diagnostics,
    canonical_hash,
    input_fingerprint,
    load_locked_bindings,
    load_state,
    product_state_paths_diagnostics,
    state_path_for,
)
from pml.validator import Diagnostic, UniqueKeyLoader, _path


SCHEMA = Path(__file__).resolve().parents[2] / "schema" / "verification-report.schema.json"
MAX_REPORT_FILE_BYTES = 1024 * 1024


def ingest_report(
    report_path: Path,
    repo_root: Path,
    definition: dict[str, Any],
    probes: dict[str, dict[str, Any]],
    locked_bindings: LockedBindings | None = None,
    *,
    definition_source: Path | None = None,
) -> list[Diagnostic]:
    if locked_bindings is None:
        locked_bindings, lock_diagnostics = load_locked_bindings(
            repo_root, definition, definition_source
        )
        if locked_bindings is None:
            return lock_diagnostics

    diagnostics: list[Diagnostic] = []
    try:
        with report_path.open("rb") as stream:
            encoded_report = stream.read(MAX_REPORT_FILE_BYTES + 1)
    except OSError as exc:
        return [Diagnostic(str(report_path), "yaml", str(exc))]
    if len(encoded_report) > MAX_REPORT_FILE_BYTES:
        return [Diagnostic(
            str(report_path),
            "report-size",
            f"verification report exceeds the {MAX_REPORT_FILE_BYTES}-byte tooling limit",
        )]
    try:
        report = yaml.load(encoded_report.decode("utf-8"), Loader=UniqueKeyLoader)
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        return [Diagnostic(str(report_path), "yaml", str(exc))]
    if not isinstance(report, dict):
        return [Diagnostic(
            str(report_path), "structure", "a verification report must be a mapping"
        )]
    schema = json.loads(SCHEMA.read_text())
    for error in sorted(
        Draft202012Validator(schema, format_checker=FORMAT_CHECKER).iter_errors(report),
        key=lambda item: list(item.absolute_path),
    ):
        diagnostics.append(Diagnostic(f"{report_path}:{_path(error.absolute_path)}", "schema", error.message))
    if diagnostics:
        return diagnostics

    checks = report.get("checks", [])
    implementation = report.get("implementation", [])
    product_obligations = list(enumerate_obligations(definition))
    architecture_obligations = list(enumerate_architecture_obligations(definition))
    obligations = {
        item.id: item for item in product_obligations + architecture_obligations
    }
    nodes = dict(list(iter_nodes(definition)) + list(iter_architecture(definition)))
    bindings = locked_bindings.document
    binding_map = bindings["bindings"]
    declared_targets = set(report["targets"])

    for index, node_id in enumerate(report["targets"]):
        if node_id not in nodes:
            diagnostics.append(Diagnostic(
                f"{report_path}:targets[{index}]",
                "undefined-reference",
                f"unknown target '{node_id}'",
            ))

    implementation_targets: set[str] = set()
    for index, assessment in enumerate(implementation):
        target = obligations.get(assessment["target"])
        location = f"{report_path}:implementation[{index}]"
        if assessment["target"] in implementation_targets:
            diagnostics.append(Diagnostic(
                f"{location}.target",
                "duplicate-implementation",
                f"duplicate implementation assessment for '{assessment['target']}'",
            ))
        implementation_targets.add(assessment["target"])
        if target is None:
            diagnostics.append(Diagnostic(
                f"{location}.target",
                "undefined-reference",
                f"unknown obligation '{assessment['target']}'",
            ))
        elif target.node_id not in declared_targets:
            diagnostics.append(Diagnostic(
                f"{location}.target",
                "undeclared-target",
                f"obligation belongs to undeclared target '{target.node_id}'",
            ))
    verification_keys: set[tuple[str, ...]] = set()
    for index, check in enumerate(checks):
        target = obligations.get(check["target"])
        location = f"{report_path}:checks[{index}]"
        if check["method"] == "deterministic_probe":
            verification_key = (
                check["target"], check["method"], check["probe"]
            )
        else:
            verification_key = (check["target"], check["method"])
        if verification_key in verification_keys:
            diagnostics.append(Diagnostic(
                location,
                "duplicate-check",
                "duplicate verification check for the same approved evidence lane",
            ))
        verification_keys.add(verification_key)
        if target is None:
            diagnostics.append(Diagnostic(f"{location}.target", "undefined-reference", f"unknown obligation '{check['target']}'"))
            continue
        if target.node_id not in declared_targets:
            diagnostics.append(Diagnostic(
                f"{location}.target",
                "undeclared-target",
                f"obligation belongs to undeclared target '{target.node_id}'",
            ))
        plan = verification_plan(bindings, target)
        if not plan:
            diagnostics.append(Diagnostic(
                f"{location}.target",
                "missing-verification-plan",
                "obligation has no approved verification plan",
            ))
            continue
        if check["method"] not in required_methods(plan):
            diagnostics.append(Diagnostic(f"{location}.method", "unexpected-evidence", f"'{check['method']}' is not required by the approved obligation"))
        if check["method"] != "deterministic_probe" and "evidence" in check:
            diagnostics.append(Diagnostic(
                f"{location}.evidence",
                "unexpected-evidence",
                "artifacts are recorded only for deterministic probe evidence",
            ))
        if check["method"] == "deterministic_probe":
            probe = probes.get(check["probe"])
            configured = plan.get("probes", {})
            if probe is None:
                diagnostics.append(Diagnostic(f"{location}.probe", "undefined-reference", f"unknown approved probe '{check['probe']}'"))
            elif probe["verifies"] != check["target"]:
                diagnostics.append(Diagnostic(f"{location}.probe", "probe-target", "approved probe verifies a different obligation"))
            elif check["probe"] not in configured:
                diagnostics.append(Diagnostic(f"{location}.probe", "unbound-probe", "probe has no approved coverage binding for this obligation"))
    if diagnostics:
        return diagnostics

    touched_nodes = {
        obligations[item["target"]].node_id
        for item in implementation + checks
    }
    product_state_paths = [
        state_path_for(repo_root, node_id)
        for node_id in touched_nodes
        if not node_id.startswith("architecture.")
    ]
    if product_state_paths:
        diagnostics.extend(product_state_paths_diagnostics(
            repo_root, product_state_paths
        ))
    if any(node_id.startswith("architecture.") for node_id in touched_nodes):
        diagnostics.extend(architecture_state_root_diagnostics(repo_root))
    if diagnostics:
        return diagnostics
    states: dict[str, tuple[Path, dict[str, Any], str]] = {}
    for node_id in touched_nodes:
        node = nodes[node_id]
        current_definition_hash = canonical_hash(node)
        if node_id.startswith("architecture."):
            paths = bindings.get("architecture", {}).get(
                node_id.removeprefix("architecture."), {}
            ).get("paths", [])
            node_obligations = list(
                enumerate_architecture_obligations(definition, node_id)
            )
        else:
            paths = binding_map.get(node_id, {}).get("paths", [])
            node_obligations = list(enumerate_obligations(definition, node_id))
        current_input = input_fingerprint(repo_root, paths)
        state_path = state_path_for(repo_root, node_id)
        if node_id.startswith("architecture.") and state_path.is_symlink():
            diagnostics.append(Diagnostic(
                str(state_path),
                "state-path",
                "architecture state file must not be a symbolic link",
            ))
            continue
        state, state_errors = load_state(state_path)
        if state_errors:
            diagnostics.extend(state_errors)
            continue
        if state is None:
            state = {
                "pml_state": "0.1",
                "node": node_id,
                "obligations": {
                    obligation.id: {"implemented": "unknown", "evidence": {}}
                    for obligation in node_obligations
                },
            }
        elif (
            state["definition_hash"] != current_definition_hash
            or state["bindings_digest"] != locked_bindings.digest
        ):
            for obligation_state in state["obligations"].values():
                obligation_state["evidence"] = {}
        state["obligations"] = {
            obligation.id: state["obligations"].get(
                obligation.id, {"implemented": "unknown", "evidence": {}}
            )
            for obligation in node_obligations
        }
        state["definition_hash"] = current_definition_hash
        state["bindings_digest"] = locked_bindings.digest
        state["input_fingerprint"] = current_input
        related_nodes = set(node.get("related_to", [])) if not node_id.startswith("architecture.") else set()
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

    if diagnostics:
        return diagnostics

    report_digest = canonical_hash(report)
    for assessment in implementation:
        obligation = obligations[assessment["target"]]
        _, state, _ = states[obligation.node_id]
        obligation_state = state["obligations"][obligation.id]
        obligation_state["implemented"] = assessment["status"]
        obligation_state["implementation"] = {
            "status": assessment["status"],
            "observation": assessment["observation"],
            "report_id": report["verification"],
            "report_digest": report_digest,
            "recorded": report["recorded"],
            "verifier": dict(report["verifier"]),
        }

    for check in checks:
        obligation = obligations[check["target"]]
        _, state, current_input = states[obligation.node_id]
        evidence = state["obligations"][obligation.id]["evidence"]
        record: dict[str, Any] = {
            "result": check["result"],
            "input_fingerprint": current_input,
            "recorded": report["recorded"],
            "observation": check["observation"],
            "report_id": report["verification"],
            "report_digest": report_digest,
            "verifier": dict(report["verifier"]),
        }
        if check["method"] == "deterministic_probe":
            probe_id = check["probe"]
            record["probe"] = probe_id
            record["probe_fingerprint"] = canonical_hash(probes[probe_id])
            if "evidence" in check:
                record["artifacts"] = check["evidence"]
            evidence.setdefault("deterministic_probe", {})[probe_id] = record
        elif check["method"] == "agent_judgment":
            record["reproduction"] = check["reproduction"]
            evidence["agent_judgment"] = record
        else:
            record["attester"] = check["attester"]
            evidence["human_attestation"] = record

    serialized_states: list[tuple[Path, bytes]] = []
    for state_path, state, _ in states.values():
        encoded = yaml.safe_dump(state, sort_keys=False).encode("utf-8")
        if len(encoded) > MAX_STATE_FILE_BYTES:
            diagnostics.append(Diagnostic(
                str(state_path),
                "state-size",
                f"generated state exceeds the {MAX_STATE_FILE_BYTES}-byte tooling limit",
            ))
            continue
        serialized_states.append((state_path, encoded))
    if diagnostics:
        return diagnostics

    for state_path, encoded in serialized_states:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_bytes(encoded)
    return []
