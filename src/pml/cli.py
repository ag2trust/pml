"""Command-line interface for PML validation."""

from __future__ import annotations

import argparse
from pathlib import Path

from pml.validator import validate_file


def main() -> int:
    parser = argparse.ArgumentParser(prog="pml")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate", help="validate a PML definition")
    validate_parser.add_argument("path", type=Path)
    args = parser.parse_args()

    diagnostics = validate_file(args.path)
    for diagnostic in diagnostics:
        print(diagnostic.format())
    if diagnostics:
        print(f"PML INVALID: {len(diagnostics)} violation(s)")
        return 1
    print(f"PML VALID: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

