"""Strict loading and semantic validation of approved probe definitions."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator

from pml.obligations import enumerate_obligations, verification_plan
from pml.project_state import canonical_hash
from pml.validator import Diagnostic, _load, _path


SCHEMA = Path(__file__).resolve().parents[2] / "schema" / "pml-probe.schema.json"
VARIABLE = re.compile(r"\{([a-z][a-z0-9_]*)\}")


def probe_fingerprint(probe: dict[str, Any]) -> str:
    return canonical_hash(probe)


def load_probes(
    path: Path,
    definition: dict[str, Any],
    bindings: dict[str, Any] | None = None,
) -> tuple[dict[str, dict[str, Any]], list[Diagnostic]]:
    sources = sorted(path.rglob("*.probe.yaml")) if path.is_dir() else [path]
    diagnostics: list[Diagnostic] = []
    probes: dict[str, dict[str, Any]] = {}
    schema = json.loads(SCHEMA.read_text())
    obligations = {item.id: item for item in enumerate_obligations(definition)}
    actors = set(definition.get("actors", {}))

    if not sources or (path.is_dir() and not sources):
        return {}, [Diagnostic(str(path), "structure", "no *.probe.yaml files found")]
    for source in sources:
        probe, errors = _load(source)
        diagnostics.extend(errors)
        if probe is None:
            continue
        schema_errors = list(Draft202012Validator(schema).iter_errors(probe))
        for error in sorted(schema_errors, key=lambda item: list(item.absolute_path)):
            diagnostics.append(Diagnostic(f"{source}:{_path(error.absolute_path)}", "schema", error.message))
        if schema_errors:
            continue
        probe_id = probe["probe"]
        if probe_id in probes:
            diagnostics.append(Diagnostic(f"{source}:probe", "duplicate-probe", f"probe '{probe_id}' is already defined"))
        else:
            probes[probe_id] = probe
        obligation = obligations.get(probe["verifies"])
        if obligation is None:
            diagnostics.append(Diagnostic(f"{source}:verifies", "undefined-reference", f"unknown obligation '{probe['verifies']}'"))
        elif bindings is not None:
            configured = verification_plan(bindings, obligation).get("probes", {})
            if probe_id not in configured:
                diagnostics.append(Diagnostic(f"{source}:probe", "unbound-probe", "probe has no approved coverage binding"))

        captured: set[str] = set()
        for index, step in enumerate(probe["steps"]):
            serialized = json.dumps(step)
            for variable in VARIABLE.findall(serialized):
                if variable not in captured:
                    diagnostics.append(Diagnostic(f"{source}:steps[{index}]", "undefined-variable", f"variable '{variable}' is used before capture"))
            actor = step.get("as")
            if actor is not None and actor not in actors:
                diagnostics.append(Diagnostic(f"{source}:steps[{index}].as", "undefined-reference", f"unknown actor '{actor}'"))
            for variable in step.get("capture", {}):
                if variable in captured:
                    diagnostics.append(Diagnostic(f"{source}:steps[{index}].capture.{variable}", "duplicate-capture", f"variable '{variable}' is already captured"))
                captured.add(variable)
    return probes, diagnostics


def missing_probe_diagnostics(
    probes: dict[str, dict[str, Any]],
    definition: dict[str, Any],
    bindings: dict[str, Any],
) -> list[Diagnostic]:
    available = set(probes)
    diagnostics: list[Diagnostic] = []
    for obligation in enumerate_obligations(definition):
        for probe_id in verification_plan(bindings, obligation).get("probes", {}):
            if probe_id not in available:
                diagnostics.append(Diagnostic(
                    obligation.id,
                    "missing-probe",
                    f"approved probe '{probe_id}' has no definition",
                ))
    return diagnostics
