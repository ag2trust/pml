"""Validation and fingerprinting for product-local .pml metadata."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from pml.obligations import enumerate_obligations, iter_nodes
from pml.validator import Diagnostic, _load, _path


ROOT = Path(__file__).resolve().parents[2]


def _schema(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "schema" / name).read_text())


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def input_fingerprint(repo_root: Path, paths: list[str]) -> str:
    """Hash path names and content deterministically, including missing bindings."""

    records: list[tuple[str, str]] = []
    resolved_root = repo_root.resolve()
    for binding in sorted(paths):
        target = repo_root / binding.rstrip("/")
        try:
            target.resolve().relative_to(resolved_root)
        except ValueError:
            records.append((binding, "outside-repository"))
            continue
        if target.is_file():
            records.append((target.relative_to(repo_root).as_posix(), hashlib.sha256(target.read_bytes()).hexdigest()))
        elif target.is_dir():
            for child in sorted(item for item in target.rglob("*") if item.is_file()):
                relative = child.relative_to(repo_root)
                if relative.parts[:2] == (".pml", "state"):
                    continue
                records.append((relative.as_posix(), hashlib.sha256(child.read_bytes()).hexdigest()))
        else:
            records.append((binding, "missing"))
    return canonical_hash(records)


def _schema_diagnostics(path: Path, document: dict[str, Any], schema_name: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    validator = Draft202012Validator(_schema(schema_name), format_checker=Draft202012Validator.FORMAT_CHECKER)
    for error in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path)):
        diagnostics.append(Diagnostic(f"{path}:{_path(error.absolute_path)}", "schema", error.message))
    return diagnostics


def validate_product_state(repo_root: Path, definition: dict[str, Any]) -> list[Diagnostic]:
    """Validate lock, bindings and state, including current-input fingerprints."""

    diagnostics: list[Diagnostic] = []
    metadata = repo_root / ".pml"
    lock_path = metadata / "pml.lock"
    bindings_path = metadata / "bindings.yaml"

    lock, errors = _load(lock_path)
    diagnostics.extend(errors)
    if lock is not None:
        lock_schema_errors = _schema_diagnostics(lock_path, lock, "pml-lock.schema.json")
        diagnostics.extend(lock_schema_errors)
        if not lock_schema_errors and lock["definition"]["digest"] != canonical_hash(definition):
            diagnostics.append(Diagnostic(
                f"{lock_path}:definition.digest",
                "definition-digest",
                "lock digest does not match the loaded approved definition",
            ))

    bindings, errors = _load(bindings_path)
    diagnostics.extend(errors)
    if bindings is None:
        return diagnostics
    binding_schema_errors = _schema_diagnostics(bindings_path, bindings, "pml-bindings.schema.json")
    diagnostics.extend(binding_schema_errors)
    if binding_schema_errors:
        return diagnostics

    nodes = dict(iter_nodes(definition))
    obligations = {item.id: item for item in enumerate_obligations(definition)}
    binding_map = bindings["bindings"]
    for node_id in binding_map:
        if node_id not in nodes:
            diagnostics.append(Diagnostic(f"{bindings_path}:bindings.{node_id}", "undefined-reference", f"unknown node '{node_id}'"))

    state_root = metadata / "state"
    for node_id in nodes:
        if node_id not in binding_map:
            diagnostics.append(Diagnostic(f"{bindings_path}:bindings", "missing-binding", f"node '{node_id}' has no binding"))
        expected_path = state_root.joinpath(*node_id.split(".")).with_suffix(".state.yaml")
        if not expected_path.is_file():
            diagnostics.append(Diagnostic(str(expected_path), "missing-state", f"node '{node_id}' has no state file"))
    resolved_root = repo_root.resolve()
    for node_id, binding in binding_map.items():
        for bound_path in binding["paths"]:
            try:
                (repo_root / bound_path.rstrip("/")).resolve().relative_to(resolved_root)
            except ValueError:
                diagnostics.append(Diagnostic(f"{bindings_path}:bindings.{node_id}.paths", "outside-repository", f"binding '{bound_path}' resolves outside the product repository"))

    for state_path in sorted(state_root.rglob("*.state.yaml")) if state_root.exists() else []:
        state, errors = _load(state_path)
        diagnostics.extend(errors)
        if state is None:
            continue
        state_schema_errors = _schema_diagnostics(state_path, state, "pml-state.schema.json")
        diagnostics.extend(state_schema_errors)
        if state_schema_errors:
            continue
        node_id = state["node"]
        if node_id not in nodes:
            diagnostics.append(Diagnostic(f"{state_path}:node", "undefined-reference", f"unknown node '{node_id}'"))
            continue
        expected_path = state_root.joinpath(*node_id.split(".")).with_suffix(".state.yaml")
        if state_path != expected_path:
            diagnostics.append(Diagnostic(str(state_path), "state-path", f"state for '{node_id}' must be at {expected_path}"))
        expected_definition_hash = canonical_hash(nodes[node_id])
        if state["definition_hash"] != expected_definition_hash:
            diagnostics.append(Diagnostic(f"{state_path}:definition_hash", "definition-mismatch", "state does not match the approved node definition"))
        node_binding = binding_map.get(node_id)
        if node_binding is None:
            diagnostics.append(Diagnostic(f"{state_path}:node", "missing-binding", f"node '{node_id}' has no binding"))
        else:
            current = input_fingerprint(repo_root, node_binding["paths"])
            if state["input_fingerprint"] != current:
                diagnostics.append(Diagnostic(f"{state_path}:input_fingerprint", "sync-required", "state does not cover current bound inputs"))
        declared_dependencies = set(nodes[node_id].get("depends_on", []))
        recorded_dependencies = state.get("dependency_fingerprints", {})
        for dependency in sorted(declared_dependencies.difference(recorded_dependencies)):
            diagnostics.append(Diagnostic(f"{state_path}:dependency_fingerprints", "missing-dependency", f"state is missing dependency fingerprint '{dependency}'"))
        for dependency in sorted(set(recorded_dependencies).difference(declared_dependencies)):
            diagnostics.append(Diagnostic(f"{state_path}:dependency_fingerprints.{dependency}", "unknown-dependency", f"'{dependency}' is not declared by the node"))
        for dependency in sorted(declared_dependencies.intersection(recorded_dependencies)):
            dependency_binding = binding_map.get(dependency)
            if dependency_binding is not None:
                current_dependency = input_fingerprint(repo_root, dependency_binding["paths"])
                if recorded_dependencies[dependency] != current_dependency:
                    diagnostics.append(Diagnostic(f"{state_path}:dependency_fingerprints.{dependency}", "sync-required", f"dependency '{dependency}' has changed"))
        prefix = node_id + "."
        for obligation_id, obligation_state in state["obligations"].items():
            obligation = obligations.get(obligation_id)
            if obligation is None or not obligation_id.startswith(prefix):
                diagnostics.append(Diagnostic(f"{state_path}:obligations.{obligation_id}", "undefined-reference", f"unknown obligation '{obligation_id}' for node '{node_id}'"))
                continue
            allowed = set(obligation.required_methods)
            for method in obligation_state["evidence"]:
                if method not in allowed:
                    diagnostics.append(Diagnostic(f"{state_path}:obligations.{obligation_id}.evidence.{method}", "unexpected-evidence", f"'{method}' is not required by the approved obligation"))
            evidence = obligation_state["evidence"]
            records = list(evidence.get("deterministic_probe", {}).values())
            records.extend(
                evidence[method]
                for method in ("agent_judgment", "human_attestation")
                if method in evidence
            )
            for record in records:
                if record["input_fingerprint"] != state["input_fingerprint"]:
                    diagnostics.append(Diagnostic(
                        f"{state_path}:obligations.{obligation_id}.evidence",
                        "stale-evidence",
                        "evidence input fingerprint does not match the node state",
                    ))
        expected_obligations = {item.id for item in enumerate_obligations(definition, node_id)}
        missing = expected_obligations.difference(state["obligations"])
        for obligation_id in sorted(missing):
            diagnostics.append(Diagnostic(f"{state_path}:obligations", "missing-obligation", f"state is missing '{obligation_id}'"))

    return diagnostics
