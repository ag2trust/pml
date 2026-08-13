"""CLI conformance for read-only compiled-model output."""

from __future__ import annotations

import io
from pathlib import Path

import pml.cli as cli


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "compiled_model"


def test_compile_json_writes_the_exact_canonical_model_to_stdout(capsys) -> None:
    source = FIXTURES / "canonical.pml.yaml"

    assert cli.main(["compile", str(source), "--json"]) == 0

    captured = capsys.readouterr()
    assert captured.out.encode("utf-8") == (FIXTURES / "canonical.json").read_bytes()
    assert captured.err == ""


def test_compile_json_writes_serializer_bytes_without_text_encoding(
    monkeypatch,
) -> None:
    class BinaryStdout:
        buffer = io.BytesIO()

        def write(self, value: str) -> int:
            raise AssertionError(f"unexpected text output: {value!r}")

    source = FIXTURES / "canonical.pml.yaml"
    stdout = BinaryStdout()
    monkeypatch.setattr(cli.sys, "stdout", stdout)

    assert cli.main(["compile", str(source), "--json"]) == 0

    assert stdout.buffer.getvalue() == (FIXTURES / "canonical.json").read_bytes()


def test_compile_json_rejects_invalid_definition_without_stdout_or_writes(
    tmp_path: Path, capsys
) -> None:
    source = tmp_path / "invalid.pml.yaml"
    source.write_text(
        """pml: \"0.1-draft\"
project:
  id: invalid
  name: Invalid
  purpose: Reject this definition.
domains:
  core:
    purpose: Demonstrate invalid input.
    features:
      broken:
        purpose: This feature references no actor.
        actors: [missing]
""",
        encoding="utf-8",
    )
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    assert cli.main(["compile", str(source), "--json"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[undefined-reference] unknown actor 'missing'" in captured.err
    assert "PML INVALID: 2 violation(s)" in captured.err
    assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == before


def test_compile_requires_json_output_mode(capsys) -> None:
    source = FIXTURES / "canonical.pml.yaml"

    assert cli.main(["compile", str(source)]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "pml compile requires --json\n"
