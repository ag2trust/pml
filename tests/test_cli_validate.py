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


def test_assistant_creation_generic_warning_does_not_fail_validation(capsys) -> None:
    source = ROOT / "examples" / "assistant-creation.pml.yaml"
    warning = (
        "domains.assistants.features.creation.rules.customer_ownership.statement: "
        "[warning] [PML-W-RULE-GENERIC] rule uses a generic quantifier without "
        "naming an actor, concept, vocabulary key, or behavior\n"
    )

    assert main(["validate", str(source)]) == 0

    captured = capsys.readouterr()
    assert captured.out == f"PML VALID: {source}\n"
    assert captured.err == warning


def test_warning_diagnostics_do_not_block_compiled_or_fallback_commands(
    tmp_path: Path, capsys
) -> None:
    source = _warning_manifest(tmp_path)
    warning = (
        "domains.notes.features.creation.rules: [warning] [PML-W-RULE-COUNT] "
        "rules maps should contain no more than 7 rules\n"
    )

    assert main(["explain", str(source), "project"]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("Project\n")
    assert captured.err == warning

    assert main(["graph", str(source)]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("digraph pml {\n")
    assert captured.err == warning

    assert main(["obligations", str(source)]) == 0
    captured = capsys.readouterr()
    assert "domains.notes.features.creation.rules.rule_0\n" in captured.out
    assert captured.err == warning
