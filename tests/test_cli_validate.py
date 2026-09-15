"""CLI validation severity coverage."""

from __future__ import annotations

from pathlib import Path

import yaml

from pml.cli import main


ROOT = Path(__file__).resolve().parents[1]


def _warning_manifest(tmp_path: Path) -> Path:
    document = yaml.safe_load((ROOT / "examples" / "minimal.pml.yaml").read_text())
    document["domains"]["notes"]["features"]["creation"]["rules"] = {
        f"rule_{index}": {"statement": f"The system MUST meet requirement {index}."}
        for index in range(8)
    }
    source = tmp_path / "warning.pml.yaml"
    source.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return source


def test_validate_warnings_succeed_unless_strict(tmp_path: Path, capsys) -> None:
    source = _warning_manifest(tmp_path)
    warning = (
        "domains.notes.features.creation.rules: [warning] [PML-W-RULE-COUNT] "
        "rules maps should contain no more than 7 rules\n"
    )

    assert main(["validate", str(source)]) == 0

    captured = capsys.readouterr()
    assert captured.out == f"PML VALID: {source}\n"
    assert captured.err == warning

    assert main(["validate", str(source), "--strict"]) == 1

    captured = capsys.readouterr()
    assert captured.out == "PML INVALID: 1 violation(s)\n"
    assert captured.err == warning
