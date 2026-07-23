"""Command-line interface for PML validation."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from pml.obligations import enumerate_obligations, iter_nodes
from pml.project_state import validate_product_state
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
    status_parser = subparsers.add_parser("status", help="show derived product state")
    status_parser.add_argument("manifest", type=Path)
    status_parser.add_argument("product_root", type=Path)
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
        for node in product_status(args.product_root, document):
            print(f"{node.node_id} implementation={node.implementation_percent:.0f}% verification={node.verification_percent:.0f}%")
            for obligation in node.obligations:
                print(f"  {obligation.obligation_id} {obligation.signal} {obligation.satisfied_lanes}/{obligation.required_lanes}")
        return 0
    if args.command == "check":
        document, _ = load_document(path)
        if document is None:
            return 1
        state_diagnostics = validate_product_state(args.product_root, document)
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
