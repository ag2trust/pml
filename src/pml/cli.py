"""Command-line interface for PML validation."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from pml.obligations import enumerate_obligations, iter_nodes
from pml.ingest import ingest_report
from pml.probes import load_probes, missing_probe_diagnostics
from pml.project_state import validate_probe_evidence, validate_product_state
from pml.status import product_status
from pml.validator import load_document, validate_file


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pml")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate", help="validate a PML definition")
    validate_parser.add_argument("path", type=Path)
    obligations_parser = subparsers.add_parser(
        "obligations", help="print stable obligation IDs"
    )
    obligations_parser.add_argument("manifest", type=Path)
    obligations_parser.add_argument("node_id", nargs="?")
    check_parser = subparsers.add_parser("check", help="validate product-local PML state")
    check_parser.add_argument("manifest", type=Path)
    check_parser.add_argument("product_root", type=Path)
    check_parser.add_argument("--probes", type=Path)
    status_parser = subparsers.add_parser("status", help="show derived product state")
    status_parser.add_argument("manifest", type=Path)
    status_parser.add_argument("product_root", type=Path)
    probes_parser = subparsers.add_parser("validate-probes", help="validate approved probe definitions")
    probes_parser.add_argument("manifest", type=Path)
    probes_parser.add_argument("probes", type=Path)
    probes_parser.add_argument("--require-complete", action="store_true")
    ingest_parser = subparsers.add_parser("ingest-report", help="ingest verification evidence into product state")
    ingest_parser.add_argument("manifest", type=Path)
    ingest_parser.add_argument("product_root", type=Path)
    ingest_parser.add_argument("probes", type=Path)
    ingest_parser.add_argument("report", type=Path)
    args = parser.parse_args(argv)

    path = args.path if args.command == "validate" else args.manifest
    diagnostics = validate_file(path)
    for diagnostic in diagnostics:
        print(diagnostic.format())
    if diagnostics:
        print(f"PML INVALID: {len(diagnostics)} violation(s)")
        return 1
    if args.command == "status":
        document, _ = load_document(path)
        assert document is not None
        for node in product_status(args.product_root, document):
            print(f"{node.node_id} implementation={node.implementation_percent:.0f}% verification={node.verification_percent:.0f}%")
            for obligation in node.obligations:
                print(f"  {obligation.obligation_id} {obligation.signal} {obligation.satisfied_lanes}/{obligation.required_lanes}")
        return 0
    if args.command == "validate-probes":
        document, _ = load_document(path)
        assert document is not None
        probes, probe_diagnostics = load_probes(args.probes, document)
        if args.require_complete:
            probe_diagnostics.extend(missing_probe_diagnostics(probes, document))
        for diagnostic in probe_diagnostics:
            print(diagnostic.format())
        if probe_diagnostics:
            print(f"PML PROBES INVALID: {len(probe_diagnostics)} violation(s)")
            return 1
        print(f"PML PROBES VALID: {args.probes}")
        return 0
    if args.command == "ingest-report":
        document, _ = load_document(path)
        assert document is not None
        probes, ingest_diagnostics = load_probes(args.probes, document)
        if not ingest_diagnostics:
            ingest_diagnostics = ingest_report(
                args.report, args.product_root, document, probes
            )
        for diagnostic in ingest_diagnostics:
            print(diagnostic.format())
        if ingest_diagnostics:
            print(f"PML REPORT NOT INGESTED: {len(ingest_diagnostics)} violation(s)")
            return 1
        print(f"PML REPORT INGESTED: {args.report}")
        return 0
    if args.command == "check":
        document, _ = load_document(path)
        assert document is not None
        state_diagnostics = validate_product_state(args.product_root, document)
        if args.probes is not None:
            probes, probe_diagnostics = load_probes(args.probes, document)
            state_diagnostics.extend(probe_diagnostics)
            state_diagnostics.extend(missing_probe_diagnostics(probes, document))
            if not probe_diagnostics:
                state_diagnostics.extend(validate_probe_evidence(args.product_root, document, probes))
        for diagnostic in state_diagnostics:
            print(diagnostic.format())
        if state_diagnostics:
            print(f"PML STATE INVALID: {len(state_diagnostics)} violation(s)")
            return 1
        print(f"PML STATE VALID: {args.product_root}")
        return 0
    if args.command == "obligations":
        document, _ = load_document(path)
        assert document is not None
        node_ids = {node_id for node_id, _ in iter_nodes(document)}
        if args.node_id is not None and args.node_id not in node_ids:
            print(f"{args.node_id}: [unknown-node] node does not exist")
            return 1
        for obligation in enumerate_obligations(document, args.node_id):
            print(obligation.id)
        return 0
    print(f"PML VALID: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
