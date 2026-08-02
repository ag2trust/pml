"""Command-line interface for PML validation."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from pml.ingest import ingest_report
from pml.obligations import (
    enumerate_architecture_obligations,
    enumerate_obligations,
    iter_architecture,
    iter_nodes,
)
from pml.probes import load_probes, missing_probe_diagnostics
from pml.project_state import (
    load_bindings,
    load_locked_bindings,
    validate_probe_evidence,
    validate_product_state,
    validate_architecture_state,
)
from pml.status import architecture_status, product_status
from pml.validator import Diagnostic, load_document, validate_file


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
    check_parser.add_argument("--probes", type=Path, help="approved probe definitions to validate against state evidence")
    status_parser = subparsers.add_parser("status", help="show derived product state")
    status_parser.add_argument("manifest", type=Path)
    status_parser.add_argument("product_root", type=Path)
    architecture_status_parser = subparsers.add_parser("architecture-status", help="show derived architecture conformance")
    architecture_status_parser.add_argument("manifest", type=Path)
    architecture_status_parser.add_argument("product_root", type=Path)
    probes_parser = subparsers.add_parser("validate-probes", help="validate approved probe definitions")
    probes_parser.add_argument("manifest", type=Path)
    probes_parser.add_argument("probes", type=Path)
    probes_parser.add_argument("--bindings", type=Path, help="explicit owner bindings used only to validate probe coverage")
    probes_parser.add_argument("--require-complete", action="store_true")
    ingest_parser = subparsers.add_parser(
        "ingest-report", help="ingest verification evidence into product state"
    )
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
        if document is None:
            return 1
        locked_bindings, state_diagnostics = load_locked_bindings(
            args.product_root, document, path
        )
        if locked_bindings is None:
            for diagnostic in state_diagnostics:
                print(diagnostic.format())
            print(f"PML STATUS UNAVAILABLE: {len(state_diagnostics)} violation(s)")
            return 1
        status_diagnostics: list[Diagnostic] = []
        nodes = product_status(
            args.product_root,
            document,
            definition_source=path,
            locked_bindings=locked_bindings,
            state_diagnostics=status_diagnostics,
        )
        if status_diagnostics:
            for diagnostic in status_diagnostics:
                print(diagnostic.format())
            print(
                f"PML STATUS UNAVAILABLE: {len(status_diagnostics)} violation(s)"
            )
            return 1
        for node in nodes:
            print(f"{node.node_id} implementation={node.implementation_percent:.0f}% verification={node.verification_percent:.0f}%")
            for obligation in node.obligations:
                print(f"  {obligation.obligation_id} {obligation.signal} {obligation.verification_percent:.0f}%")
        return 0
    if args.command == "architecture-status":
        document, _ = load_document(path)
        if document is None:
            return 1
        locked_bindings, state_diagnostics = load_locked_bindings(
            args.product_root, document, path
        )
        if locked_bindings is None:
            for diagnostic in state_diagnostics:
                print(diagnostic.format())
            print(
                f"PML ARCHITECTURE STATUS UNAVAILABLE: "
                f"{len(state_diagnostics)} violation(s)"
            )
            return 1
        status_diagnostics: list[Diagnostic] = []
        nodes = architecture_status(
            args.product_root,
            document,
            definition_source=path,
            locked_bindings=locked_bindings,
            state_diagnostics=status_diagnostics,
        )
        if status_diagnostics:
            for diagnostic in status_diagnostics:
                print(diagnostic.format())
            print(
                "PML ARCHITECTURE STATUS UNAVAILABLE: "
                f"{len(status_diagnostics)} violation(s)"
            )
            return 1
        for node in nodes:
            print(f"{node.node_id} implementation={node.implementation_percent:.0f}% verification={node.verification_percent:.0f}%")
            for obligation in node.obligations:
                print(f"  {obligation.obligation_id} {obligation.signal} {obligation.verification_percent:.0f}%")
        return 0
    if args.command == "validate-probes":
        document, _ = load_document(path)
        if document is None:
            return 1
        bindings = None
        binding_diagnostics: list[Diagnostic] = []
        if args.bindings is not None:
            bindings, binding_diagnostics = load_bindings(args.bindings, document)
        probes, probe_diagnostics = load_probes(args.probes, document, bindings)
        probe_diagnostics.extend(binding_diagnostics)
        if args.require_complete:
            if args.bindings is None:
                probe_diagnostics.append(
                    Diagnostic(str(args.probes), "missing-bindings", "--require-complete requires --bindings")
                )
            elif bindings is not None:
                probe_diagnostics.extend(missing_probe_diagnostics(probes, document, bindings))
        for diagnostic in probe_diagnostics:
            print(diagnostic.format())
        if probe_diagnostics:
            print(f"PML PROBES INVALID: {len(probe_diagnostics)} violation(s)")
            return 1
        print(f"PML PROBES VALID: {args.probes}")
        return 0
    if args.command == "ingest-report":
        document, _ = load_document(path)
        if document is None:
            return 1
        locked_bindings, binding_diagnostics = load_locked_bindings(
            args.product_root, document, path
        )
        ingest_diagnostics = list(binding_diagnostics)
        bindings = (
            locked_bindings.document if locked_bindings is not None else None
        )
        probes, probe_diagnostics = load_probes(
            args.probes, document, bindings
        )
        ingest_diagnostics.extend(probe_diagnostics)
        if locked_bindings is not None and not ingest_diagnostics:
            ingest_diagnostics = ingest_report(
                args.report,
                args.product_root,
                document,
                probes,
                definition_source=path,
                locked_bindings=locked_bindings,
            )
        for diagnostic in ingest_diagnostics:
            print(diagnostic.format())
        if ingest_diagnostics:
            print(
                f"PML REPORT NOT INGESTED: {len(ingest_diagnostics)} violation(s)"
            )
            return 1
        print(f"PML REPORT INGESTED: {args.report}")
        return 0
    if args.command == "check":
        document, _ = load_document(path)
        if document is None:
            return 1
        locked_bindings, state_diagnostics = load_locked_bindings(
            args.product_root, document, path
        )
        if locked_bindings is not None:
            state_diagnostics.extend(validate_product_state(
                args.product_root,
                document,
                definition_source=path,
                locked_bindings=locked_bindings,
            ))
            state_diagnostics.extend(validate_architecture_state(
                args.product_root,
                document,
                definition_source=path,
                locked_bindings=locked_bindings,
            ))
        if (
            args.probes is not None
            and locked_bindings is not None
            and not state_diagnostics
        ):
            bindings = locked_bindings.document
            probes, probe_diagnostics = load_probes(args.probes, document, bindings)
            state_diagnostics.extend(probe_diagnostics)
            state_diagnostics.extend(missing_probe_diagnostics(probes, document, bindings))
            if not probe_diagnostics:
                state_diagnostics.extend(validate_probe_evidence(
                    args.product_root,
                    document,
                    probes,
                    definition_source=path,
                    locked_bindings=locked_bindings,
                ))
        for diagnostic in state_diagnostics:
            print(diagnostic.format())
        if state_diagnostics:
            print(f"PML STATE INVALID: {len(state_diagnostics)} violation(s)")
            return 1
        print(f"PML STATE VALID: {args.product_root}")
        return 0
    if args.command == "obligations":
        document, _ = load_document(path)
        if document is None:
            return 1
        node_ids = {
            node_id
            for node_id, _ in list(iter_nodes(document)) + list(iter_architecture(document))
        }
        if args.node_id is not None and args.node_id not in node_ids:
            print(f"{args.node_id}: [unknown-node] node does not exist")
            return 1
        for obligation in enumerate_obligations(document, args.node_id):
            print(obligation.id)
        for obligation in enumerate_architecture_obligations(document, args.node_id):
            print(obligation.id)
        return 0
    print(f"PML VALID: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
