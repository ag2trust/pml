"""Validation and fingerprinting for product-local .pml metadata."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from pml.obligations import (
    enumerate_architecture_obligations,
    enumerate_obligations,
    iter_architecture,
    iter_nodes,
    required_methods,
    verification_coverage,
    verification_plan,
)
from pml.validator import Diagnostic, _load, _path, load_document


ROOT = Path(__file__).resolve().parents[2]


def state_path_for(repo_root: Path, node_id: str) -> Path:
    """Return the isolated generated-state location for a conformance scope."""

    if node_id.startswith("architecture."):
        return repo_root / ".pml" / "architecture" / f"{node_id.removeprefix('architecture.')}.state.yaml"
    return (repo_root / ".pml" / "state" / Path(*node_id.split("."))).with_suffix(".state.yaml")


def _schema(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "schema" / name).read_text())


def canonical_hash(value: Any) -> str:
    """Hash the canonical UTF-8 JSON representation of a validated artifact."""

    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def bindings_digest(bindings: dict[str, Any]) -> str:
    """Return the canonical digest of a validated bindings document."""

    return canonical_hash(bindings)


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


def _bindings_semantic_diagnostics(
    path: Path,
    bindings: dict[str, Any],
    definition: dict[str, Any],
    repo_root: Path | None,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    nodes = dict(iter_nodes(definition))
    binding_map = bindings["bindings"]

    for node_id, binding in binding_map.items():
        if node_id not in nodes:
            diagnostics.append(Diagnostic(
                f"{path}:bindings.{node_id}",
                "undefined-reference",
                f"unknown node '{node_id}'",
            ))
            continue
        expected = {
            item.id for item in enumerate_obligations(definition, node_id)
        }
        configured = set(binding.get("verification", {}))
        for obligation_id in sorted(expected.difference(configured)):
            diagnostics.append(Diagnostic(
                f"{path}:bindings.{node_id}.verification",
                "missing-verification-plan",
                f"obligation '{obligation_id}' has no verification plan",
            ))
        for obligation_id in sorted(configured.difference(expected)):
            diagnostics.append(Diagnostic(
                f"{path}:bindings.{node_id}.verification.{obligation_id}",
                "undefined-reference",
                f"unknown obligation '{obligation_id}'",
            ))
        for obligation_id in sorted(expected.intersection(configured)):
            plan = binding["verification"][obligation_id]
            total = sum(verification_coverage(plan).values())
            if abs(total - 1.0) > 1e-9:
                diagnostics.append(Diagnostic(
                    f"{path}:bindings.{node_id}.verification.{obligation_id}",
                    "coverage-total",
                    f"verification coverage must total 1.0, got {total:g}",
                ))

    for node_id in nodes:
        if node_id not in binding_map:
            diagnostics.append(Diagnostic(
                f"{path}:bindings",
                "missing-binding",
                f"node '{node_id}' has no binding",
            ))

    if repo_root is not None:
        resolved_root = repo_root.resolve()
        for node_id, binding in binding_map.items():
            for bound_path in binding["paths"]:
                try:
                    (repo_root / bound_path.rstrip("/")).resolve().relative_to(
                        resolved_root
                    )
                except ValueError:
                    diagnostics.append(Diagnostic(
                        f"{path}:bindings.{node_id}.paths",
                        "outside-repository",
                        f"binding '{bound_path}' resolves outside the product repository",
                    ))
    return diagnostics


def load_bindings(
    path: Path,
    definition: dict[str, Any],
    repo_root: Path | None = None,
) -> tuple[dict[str, Any] | None, list[Diagnostic]]:
    """Load bindings only after structural and semantic validation."""

    bindings, diagnostics = _load(path)
    if bindings is None:
        return None, diagnostics
    schema_diagnostics = _schema_diagnostics(
        path, bindings, "pml-bindings.schema.json"
    )
    diagnostics.extend(schema_diagnostics)
    if schema_diagnostics:
        return None, diagnostics
    semantic_diagnostics = _bindings_semantic_diagnostics(
        path, bindings, definition, repo_root
    )
    diagnostics.extend(semantic_diagnostics)
    if semantic_diagnostics:
        return None, diagnostics
    return bindings, diagnostics


@dataclass(frozen=True)
class LockedBindings:
    document: dict[str, Any]
    path: Path
    digest: str


def load_locked_bindings(
    repo_root: Path,
    definition: dict[str, Any],
    definition_source: Path | None = None,
) -> tuple[LockedBindings | None, list[Diagnostic]]:
    """Resolve and validate the exact definition and bindings pinned by the lock."""

    lock_path = repo_root / ".pml" / "pml.lock"
    lock, diagnostics = _load(lock_path)
    if lock is None:
        return None, diagnostics
    lock_errors = _schema_diagnostics(lock_path, lock, "pml-lock.schema.json")
    diagnostics.extend(lock_errors)
    if lock_errors:
        return None, diagnostics

    digest_errors = False
    if lock["definition"]["digest"] != canonical_hash(definition):
        diagnostics.append(Diagnostic(
            f"{lock_path}:definition.digest",
            "definition-digest",
            "lock digest does not match the loaded approved definition",
        ))
        digest_errors = True

    source = Path(lock["definition"]["source"])
    source_path = source if source.is_absolute() else repo_root / source
    source_path = source_path.resolve()
    if not source_path.exists():
        diagnostics.append(Diagnostic(
            f"{lock_path}:definition.source",
            "definition-source",
            "locked definition source does not exist",
        ))
        return None, diagnostics
    if definition_source is None:
        diagnostics.append(Diagnostic(
            f"{lock_path}:definition.source",
            "definition-source",
            "product-state operations require the approved definition source path",
        ))
        return None, diagnostics
    approved_source_path = definition_source.resolve()
    if source_path != approved_source_path:
        diagnostics.append(Diagnostic(
            f"{lock_path}:definition.source",
            "definition-source",
            "locked definition source does not identify the loaded approved definition",
        ))
        return None, diagnostics
    source_definition, source_errors = load_document(approved_source_path)
    diagnostics.extend(source_errors)
    if source_definition is None:
        return None, diagnostics
    if canonical_hash(source_definition) != canonical_hash(definition):
        diagnostics.append(Diagnostic(
            f"{lock_path}:definition.source",
            "definition-source",
            "locked definition source content does not match the loaded approved definition",
        ))
        return None, diagnostics
    bindings_path = (
        source_path / "bindings.yaml"
        if source_path.is_dir()
        else source_path.parent / "bindings.yaml"
    )
    bindings, binding_errors = load_bindings(bindings_path, definition, repo_root)
    diagnostics.extend(binding_errors)
    if bindings is None:
        return None, diagnostics
    if lock["bindings"]["digest"] != bindings_digest(bindings):
        diagnostics.append(Diagnostic(
            f"{lock_path}:bindings.digest",
            "bindings-digest",
            "lock digest does not match the validated approved bindings",
        ))
        digest_errors = True
    if digest_errors:
        return None, diagnostics
    return LockedBindings(
        bindings, bindings_path, bindings_digest(bindings)
    ), diagnostics


def load_state(path: Path) -> tuple[dict[str, Any] | None, list[Diagnostic]]:
    """Load an existing state file only when it conforms to the state schema."""

    if not path.exists():
        return None, []
    state, diagnostics = _load(path)
    if state is None:
        return None, diagnostics
    schema_diagnostics = _schema_diagnostics(path, state, "pml-state.schema.json")
    diagnostics.extend(schema_diagnostics)
    if schema_diagnostics:
        return None, diagnostics
    return state, diagnostics


def validate_product_state(
    repo_root: Path,
    definition: dict[str, Any],
    locked_bindings: LockedBindings | None = None,
    *,
    definition_source: Path | None = None,
) -> list[Diagnostic]:
    """Validate lock, bindings and state, including current-input fingerprints."""

    diagnostics: list[Diagnostic] = []
    metadata = repo_root / ".pml"
    if locked_bindings is None:
        locked_bindings, errors = load_locked_bindings(
            repo_root, definition, definition_source
        )
        diagnostics.extend(errors)
    if locked_bindings is None:
        return diagnostics
    bindings = locked_bindings.document
    nodes = dict(iter_nodes(definition))
    obligations = {item.id: item for item in enumerate_obligations(definition)}
    binding_map = bindings["bindings"]

    state_root = metadata / "state"
    for node_id in nodes:
        expected_path = state_root.joinpath(*node_id.split(".")).with_suffix(".state.yaml")
        if not expected_path.is_file():
            diagnostics.append(Diagnostic(str(expected_path), "missing-state", f"node '{node_id}' has no state file"))

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
        if state["bindings_digest"] != locked_bindings.digest:
            diagnostics.append(Diagnostic(
                f"{state_path}:bindings_digest",
                "bindings-mismatch",
                "state does not match the approved bindings",
            ))
        node_binding = binding_map.get(node_id)
        if node_binding is None:
            diagnostics.append(Diagnostic(f"{state_path}:node", "missing-binding", f"node '{node_id}' has no binding"))
        else:
            current = input_fingerprint(repo_root, node_binding["paths"])
            if state["input_fingerprint"] != current:
                diagnostics.append(Diagnostic(f"{state_path}:input_fingerprint", "sync-required", "state does not cover current bound inputs"))
        declared_related = set(nodes[node_id].get("related_to", []))
        declared_related.update(
            other_id
            for other_id, other in nodes.items()
            if node_id in other.get("related_to", [])
        )
        recorded_related = state.get("related_fingerprints", {})
        for related in sorted(declared_related.difference(recorded_related)):
            diagnostics.append(Diagnostic(f"{state_path}:related_fingerprints", "missing-related", f"state is missing related-node fingerprint '{related}'"))
        for related in sorted(set(recorded_related).difference(declared_related)):
            diagnostics.append(Diagnostic(f"{state_path}:related_fingerprints.{related}", "unknown-related", f"'{related}' is not related to the node"))
        for related in sorted(declared_related.intersection(recorded_related)):
            related_binding = binding_map.get(related)
            if related_binding is not None:
                current_related = input_fingerprint(repo_root, related_binding["paths"])
                if recorded_related[related] != current_related:
                    diagnostics.append(Diagnostic(f"{state_path}:related_fingerprints.{related}", "sync-required", f"related node '{related}' has changed"))
        prefix = node_id + "."
        for obligation_id, obligation_state in state["obligations"].items():
            obligation = obligations.get(obligation_id)
            if obligation is None or not obligation_id.startswith(prefix):
                diagnostics.append(Diagnostic(f"{state_path}:obligations.{obligation_id}", "undefined-reference", f"unknown obligation '{obligation_id}' for node '{node_id}'"))
                continue
            allowed = set(required_methods(verification_plan(bindings, obligation)))
            for method in obligation_state["evidence"]:
                if method not in allowed:
                    diagnostics.append(Diagnostic(f"{state_path}:obligations.{obligation_id}.evidence.{method}", "unexpected-evidence", f"'{method}' is not required by the approved obligation"))
        expected_obligations = {item.id for item in enumerate_obligations(definition, node_id)}
        missing = expected_obligations.difference(state["obligations"])
        for obligation_id in sorted(missing):
            diagnostics.append(Diagnostic(f"{state_path}:obligations", "missing-obligation", f"state is missing '{obligation_id}'"))

    return diagnostics


def validate_architecture_state(
    repo_root: Path,
    definition: dict[str, Any],
    locked_bindings: LockedBindings | None = None,
    *,
    definition_source: Path | None = None,
) -> list[Diagnostic]:
    """Validate independent evidence for owner-approved architecture constraints."""

    diagnostics: list[Diagnostic] = []
    metadata = repo_root / ".pml"
    if locked_bindings is None:
        locked_bindings, errors = load_locked_bindings(
            repo_root, definition, definition_source
        )
        diagnostics.extend(errors)
    if locked_bindings is None:
        return diagnostics
    bindings = locked_bindings.document
    decisions = dict(iter_architecture(definition))
    binding_map = bindings.get("architecture", {})
    obligations = {
        item.id: item for item in enumerate_architecture_obligations(definition)
    }
    for decision_id in binding_map:
        node_id = f"architecture.{decision_id}"
        if node_id not in decisions:
            diagnostics.append(Diagnostic(f"{metadata / 'bindings.yaml'}:architecture.{decision_id}", "undefined-reference", f"unknown architecture decision '{decision_id}'"))
            continue
        expected = {
            item.id for item in enumerate_architecture_obligations(definition, node_id)
        }
        configured = set(binding_map[decision_id].get("verification", {}))
        for obligation_id in sorted(expected.difference(configured)):
            diagnostics.append(Diagnostic(f"{metadata / 'bindings.yaml'}:architecture.{decision_id}.verification", "missing-verification-plan", f"constraint '{obligation_id}' has no verification plan"))
        for obligation_id in sorted(configured.difference(expected)):
            diagnostics.append(Diagnostic(f"{metadata / 'bindings.yaml'}:architecture.{decision_id}.verification.{obligation_id}", "undefined-reference", f"unknown architecture constraint '{obligation_id}'"))
        for obligation_id in sorted(expected.intersection(configured)):
            total = sum(verification_coverage(binding_map[decision_id]["verification"][obligation_id]).values())
            if abs(total - 1.0) > 1e-9:
                diagnostics.append(Diagnostic(f"{metadata / 'bindings.yaml'}:architecture.{decision_id}.verification.{obligation_id}", "coverage-total", f"verification coverage must total 1.0, got {total:g}"))
    for node_id, decision in decisions.items():
        decision_id = node_id.removeprefix("architecture.")
        if decision_id not in binding_map:
            diagnostics.append(Diagnostic(f"{metadata / 'bindings.yaml'}:architecture", "missing-binding", f"architecture decision '{decision_id}' has no binding"))
            continue
        state_path = state_path_for(repo_root, node_id)
        if not state_path.is_file():
            diagnostics.append(Diagnostic(str(state_path), "missing-state", f"architecture decision '{node_id}' has no state file"))
            continue
        state, errors = _load(state_path)
        diagnostics.extend(errors)
        if state is None:
            continue
        schema_errors = _schema_diagnostics(state_path, state, "pml-state.schema.json")
        diagnostics.extend(schema_errors)
        if schema_errors:
            continue
        if state["node"] != node_id:
            diagnostics.append(Diagnostic(f"{state_path}:node", "undefined-reference", f"state must identify architecture decision '{node_id}'"))
            continue
        if state["definition_hash"] != canonical_hash(decision):
            diagnostics.append(Diagnostic(f"{state_path}:definition_hash", "definition-mismatch", "state does not match the approved architecture decision"))
        current = input_fingerprint(repo_root, binding_map[decision_id]["paths"])
        if state["input_fingerprint"] != current:
            diagnostics.append(Diagnostic(f"{state_path}:input_fingerprint", "sync-required", "state does not cover current bound inputs"))
        expected = {item.id for item in enumerate_architecture_obligations(definition, node_id)}
        for obligation_id in sorted(expected.difference(state["obligations"])):
            diagnostics.append(Diagnostic(f"{state_path}:obligations", "missing-obligation", f"state is missing '{obligation_id}'"))
        for obligation_id, obligation_state in state["obligations"].items():
            obligation = obligations.get(obligation_id)
            if obligation is None or obligation.node_id != node_id:
                diagnostics.append(Diagnostic(f"{state_path}:obligations.{obligation_id}", "undefined-reference", f"unknown architecture constraint '{obligation_id}'"))
                continue
            allowed = set(required_methods(verification_plan(bindings, obligation)))
            for method in obligation_state["evidence"]:
                if method not in allowed:
                    diagnostics.append(Diagnostic(f"{state_path}:obligations.{obligation_id}.evidence.{method}", "unexpected-evidence", f"'{method}' is not required by the approved constraint"))
    architecture_root = metadata / "architecture"
    for state_path in sorted(architecture_root.glob("*.state.yaml")) if architecture_root.exists() else []:
        state, errors = _load(state_path)
        if errors or state is None or "node" not in state:
            continue
        if state["node"] not in decisions:
            diagnostics.append(Diagnostic(f"{state_path}:node", "undefined-reference", f"unknown architecture decision '{state['node']}'"))
    return diagnostics


def validate_probe_evidence(
    repo_root: Path,
    definition: dict[str, Any],
    probes: dict[str, dict[str, Any]],
    locked_bindings: LockedBindings | None = None,
    *,
    definition_source: Path | None = None,
) -> list[Diagnostic]:
    """Enforce complete, current, passing evidence for every approved probe."""

    diagnostics: list[Diagnostic] = []
    metadata = repo_root / ".pml"
    if locked_bindings is None:
        locked_bindings, errors = load_locked_bindings(
            repo_root, definition, definition_source
        )
        diagnostics.extend(errors)
    if locked_bindings is None:
        return diagnostics
    bindings = locked_bindings.document
    probe_by_obligation: dict[str, dict[str, dict[str, Any]]] = {}
    for probe_id, probe in probes.items():
        probe_by_obligation.setdefault(probe["verifies"], {})[probe_id] = probe

    for node_id, _ in list(iter_nodes(definition)) + list(iter_architecture(definition)):
        state_path = state_path_for(repo_root, node_id)
        state, _ = _load(state_path)
        if state is None:
            continue
        if state.get("bindings_digest") != locked_bindings.digest:
            diagnostics.append(Diagnostic(
                f"{state_path}:bindings_digest",
                "bindings-mismatch",
                "probe evidence does not match the approved bindings",
            ))
            continue
        if node_id.startswith("architecture."):
            paths = bindings.get("architecture", {}).get(node_id.removeprefix("architecture."), {}).get("paths", [])
        else:
            paths = bindings.get("bindings", {}).get(node_id, {}).get("paths", [])
        current_input = input_fingerprint(repo_root, paths)
        enumerator = enumerate_architecture_obligations if node_id.startswith("architecture.") else enumerate_obligations
        for obligation in enumerator(definition, node_id):
            approved = probe_by_obligation.get(obligation.id, {})
            plan = verification_plan(bindings, obligation)
            if "deterministic_probe" not in required_methods(plan):
                continue
            obligation_state = state.get("obligations", {}).get(obligation.id, {})
            evidence = obligation_state.get("evidence", {}).get("deterministic_probe", {})
            configured_probes = set(plan.get("probes", {}))
            for probe_id in sorted(configured_probes.difference(approved)):
                diagnostics.append(Diagnostic(
                    f"{state_path}:obligations.{obligation.id}.evidence.deterministic_probe.{probe_id}",
                    "missing-probe-definition",
                    "verification binding names a probe with no approved definition",
                ))
            for probe_id, probe in approved.items():
                if probe_id not in configured_probes:
                    diagnostics.append(Diagnostic(
                        f"{state_path}:obligations.{obligation.id}.evidence.deterministic_probe.{probe_id}",
                        "unbound-probe",
                        "approved probe has no coverage binding",
                    ))
                    continue
                record = evidence.get(probe_id)
                location = f"{state_path}:obligations.{obligation.id}.evidence.deterministic_probe.{probe_id}"
                if record is None:
                    diagnostics.append(Diagnostic(location, "missing-probe-evidence", "approved probe has no evidence"))
                    continue
                if record["input_fingerprint"] != current_input:
                    diagnostics.append(Diagnostic(location, "stale-probe-evidence", "probe evidence does not cover current bound inputs"))
                if record["probe_fingerprint"] != canonical_hash(probe):
                    diagnostics.append(Diagnostic(location, "probe-mismatch", "evidence does not match the approved probe definition"))
                if record["result"] != "passed":
                    diagnostics.append(Diagnostic(location, "probe-failed", f"approved probe result is {record['result']}"))
            for probe_id in set(evidence).difference(approved):
                diagnostics.append(Diagnostic(
                    f"{state_path}:obligations.{obligation.id}.evidence.deterministic_probe.{probe_id}",
                    "unknown-probe-evidence",
                    "evidence does not identify an approved probe for this obligation",
                ))
    return diagnostics
