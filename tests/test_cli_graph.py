"""Conformance coverage for the read-only compiled-model graph consumer."""

from __future__ import annotations

import copy
import io
from pathlib import Path

import pytest

import pml.cli as cli
from pml.graph import graph_compiled_model, iter_explicit_graph_edges, serialize_graph_dot
from pml.validator import load_document, validate_document


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "compiled_model"
CANONICAL = FIXTURES / "canonical.pml.yaml"


def _compiled(source: Path):  # type: ignore[no-untyped-def]
    document, diagnostics = load_document(source)
    assert document is not None
    assert diagnostics == []
    resolution = validate_document(document)
    assert resolution.diagnostics == ()
    assert resolution.compiled_model is not None
    return resolution.compiled_model


def _write_manifest(tmp_path: Path, name: str, body: str) -> Path:
    source = tmp_path / name
    source.write_text(body, encoding="utf-8")
    return source


def test_graph_writes_the_exact_nonempty_golden_bytes_to_binary_stdout(monkeypatch) -> None:
    class BinaryStdout:
        buffer = io.BytesIO()

        def write(self, value: str) -> int:
            raise AssertionError(f"unexpected text output: {value!r}")

    stdout = BinaryStdout()
    monkeypatch.setattr(cli.sys, "stdout", stdout)

    assert cli.main(["graph", str(CANONICAL)]) == 0
    assert stdout.buffer.getvalue() == (FIXTURES / "canonical.graph.dot").read_bytes()


def test_graph_preserves_the_complete_explicit_edge_inventory_and_order(capsys) -> None:
    assert cli.main(["graph", str(CANONICAL)]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.encode("utf-8") == (FIXTURES / "canonical.graph.dot").read_bytes()
    assert '"record_ready" -> "domains.a_work.features.workspace.behaviors.a_start.trigger.z_ready"' in captured.out
    assert '"z_started" ->' not in captured.out
    assert captured.out.count('kind="related_to"') == 4
    assert captured.out.count('kind="use_case_membership"') == 3
    assert '"domains.a_work" [label=' not in captured.out
    assert '"ada" [label=' not in captured.out
    assert '"a_record" [label=' not in captured.out
    assert '"Alpha" [label=' not in captured.out
    assert '"domains.a_work.features.workspace.behaviors.z_finish" -> "record_ready"' not in captured.out


def test_graph_edge_iterator_retains_causal_leg_origins_and_compiled_order() -> None:
    edges = tuple(iter_explicit_graph_edges(_compiled(CANONICAL)))

    assert [(edge.meaning, edge.origin) for edge in edges[:3]] == [
        ("causal", "producer_to_signal"),
        ("causal", "signal_to_consumer_trigger"),
        ("causal", "producer_to_signal"),
    ]
    assert [(edge.meaning, edge.origin) for edge in edges[3:]] == [
        ("related_to", "related_to"),
        ("related_to", "related_to"),
        ("related_to", "related_to"),
        ("related_to", "related_to"),
        ("use_case_membership", "use_case_membership"),
        ("use_case_membership", "use_case_membership"),
        ("use_case_membership", "use_case_membership"),
    ]
    assert edges[3].declared_by == ("domains.a_work.features.workspace",)


def test_graph_writes_the_exact_empty_golden_bytes(tmp_path: Path, capsys) -> None:
    source = _write_manifest(
        tmp_path,
        "empty.pml.yaml",
        """pml: "0.1-draft"
project: {id: empty, name: Empty, purpose: Has no explicit graph edges.}
domains:
  core:
    purpose: Holds otherwise unrelated nodes.
    features:
      one:
        purpose: Has no graph relationship.
        behaviors:
          idle:
            trigger: {statement: A participant starts idling.}
            outcome: {statement: Idling completes.}
""",
    )
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    assert cli.main(["graph", str(source)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.encode("utf-8") == (FIXTURES / "empty.graph.dot").read_bytes()
    assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == before


def test_graph_preserves_multiple_consumers_and_distinct_alternative_obligations(
    tmp_path: Path, capsys
) -> None:
    source = _write_manifest(
        tmp_path,
        "alternatives.pml.yaml",
        """pml: "0.1-draft"
project: {id: alternatives, name: Alternatives, purpose: Preserve each causal endpoint.}
domains:
  core:
    purpose: Holds transition cases.
    features:
      flow:
        purpose: Connect alternative transitions.
        behaviors:
          producer:
            trigger: {statement: A participant starts producing.}
            outcome:
              one_of:
                first:
                  statement: The first result completes.
                  signal: {id: first_signal, meaning: The first result is available.}
                second:
                  statement: The second result completes.
                  signal: {id: second_signal, meaning: The second result is available.}
          consumer_one:
            trigger: {signal: first_signal}
            outcome: {statement: The first consumer completes.}
          consumer_two:
            trigger: {signal: first_signal}
            outcome: {statement: The second consumer completes.}
          alternative_consumer:
            trigger:
              one_of:
                first: {signal: first_signal}
                second: {signal: second_signal}
            outcome: {statement: The alternative consumer completes.}
""",
    )

    assert cli.main(["graph", str(source)]) == 0
    rendered = capsys.readouterr().out
    producer = "domains.core.features.flow.behaviors.producer"
    assert f'"{producer}.outcome.first" -> "first_signal"' in rendered
    assert f'"{producer}.outcome.second" -> "second_signal"' in rendered
    assert rendered.count('"first_signal" ->') == 3
    assert '"second_signal" -> "domains.core.features.flow.behaviors.alternative_consumer.trigger.second"' in rendered
    assert f'"{producer}" -> "first_signal"' not in rendered


def test_graph_collapses_reciprocal_relationships_and_orders_memberships(
    tmp_path: Path, capsys
) -> None:
    source = _write_manifest(
        tmp_path,
        "relationships.pml.yaml",
        """pml: "0.1-draft"
project: {id: relationships, name: Relationships, purpose: Retain normalized relationships.}
actors:
  user: {meaning: A participant.}
domains:
  core:
    purpose: Holds related features and behaviors.
    features:
      zeta:
        purpose: The later feature.
        related_to: [domains.core.features.alpha]
        behaviors:
          zed:
            related_to: [domains.core.features.alpha.behaviors.able]
            trigger: {statement: A participant starts zed.}
            outcome: {statement: Zed completes.}
      alpha:
        purpose: The earlier feature.
        related_to: [domains.core.features.zeta]
        use_cases:
          flow:
            actor: user
            goal: Use behaviors without an order edge.
            behaviors: [domains.core.features.alpha.behaviors.able, domains.core.features.alpha.behaviors.beta]
        behaviors:
          beta:
            trigger: {statement: A participant starts beta.}
            outcome: {statement: Beta completes.}
          able:
            related_to: [domains.core.features.zeta.behaviors.zed]
            trigger: {statement: A participant starts able.}
            outcome: {statement: Able completes.}
""",
    )

    assert cli.main(["graph", str(source)]) == 0
    rendered = capsys.readouterr().out
    assert rendered.count('kind="related_to"') == 2
    assert rendered.count('kind="use_case_membership"') == 2
    assert rendered.index('"domains.core.features.alpha" -> "domains.core.features.zeta"') < rendered.index(
        '"domains.core.features.alpha.behaviors.able" -> "domains.core.features.zeta.behaviors.zed"'
    )
    first_membership = '"domains.core.features.alpha.use_cases.flow" -> "domains.core.features.alpha.behaviors.able"'
    second_membership = '"domains.core.features.alpha.use_cases.flow" -> "domains.core.features.alpha.behaviors.beta"'
    assert rendered.index(first_membership) < rendered.index(second_membership)


def test_graph_distinguishes_authored_and_derived_relationship_edges(
    tmp_path: Path, capsys
) -> None:
    source = _write_manifest(
        tmp_path,
        "derived-relationships.pml.yaml",
        """pml: "0.1-draft"
project: {id: derived_relationships, name: Derived relationships, purpose: Render relationship provenance.}
concepts:
  note: {meaning: A Note., states: [draft, published]}
domains:
  notes:
    purpose: Holds related note features.
    features:
      create:
        purpose: Create a note.
        related_to: [domains.notes.features.archive]
        behaviors:
          create:
            trigger: {statement: A member creates a note.}
            outcome:
              statement: The note enters draft.
              signal: {id: note_created, meaning: A note was created.}
              transitions: {note: none -> draft}
      publish:
        purpose: Publish a note.
        behaviors:
          publish:
            trigger: {statement: A member publishes a note.}
            outcome:
              statement: The note becomes published.
              transitions: {note: draft -> published}
      notify:
        purpose: Notify a member.
        behaviors:
          notify:
            trigger: {signal: note_created}
            outcome: {statement: The member is notified.}
      archive:
        purpose: Archive a note.
        behaviors:
          archive:
            trigger: {statement: A member archives a note.}
            outcome: {statement: The note is archived.}
""",
    )

    assert cli.main(["graph", str(source)]) == 0
    rendered = capsys.readouterr().out
    assert (
        '"domains.notes.features.archive" -> "domains.notes.features.create" '
        '[dir="none", kind="related_to", style="dashed"]'
    ) in rendered
    assert (
        '"domains.notes.features.create" -> "domains.notes.features.publish" '
        '[dir="none", kind="derived", style="dashed"]'
    ) in rendered
    assert (
        '"domains.notes.features.create" -> "domains.notes.features.notify" '
        '[dir="none", kind="derived", style="dashed"]'
    ) in rendered


def test_graph_is_deterministic_for_reordered_source_maps(tmp_path: Path, capsys) -> None:
    first = _write_manifest(
        tmp_path,
        "first.pml.yaml",
        """pml: "0.1-draft"
project: {id: ordered, name: Ordered, purpose: Preserve map-independent graph bytes.}
domains:
  zeta:
    purpose: Later domain.
    features:
      zed:
        purpose: Later feature.
        related_to: [domains.alpha.features.able]
        behaviors:
          idle:
            trigger: {statement: A participant starts idling.}
            outcome: {statement: Idling completes.}
  alpha:
    purpose: Earlier domain.
    features:
      able:
        purpose: Earlier feature.
        related_to: [domains.zeta.features.zed]
        behaviors:
          idle:
            trigger: {statement: A participant starts idling.}
            outcome: {statement: Idling completes.}
""",
    )
    second = _write_manifest(
        tmp_path,
        "second.pml.yaml",
        """pml: "0.1-draft"
project: {purpose: Preserve map-independent graph bytes., name: Ordered, id: ordered}
domains:
  alpha:
    features:
      able:
        related_to: [domains.zeta.features.zed]
        purpose: Earlier feature.
        behaviors:
          idle:
            trigger: {statement: A participant starts idling.}
            outcome: {statement: Idling completes.}
    purpose: Earlier domain.
  zeta:
    features:
      zed:
        related_to: [domains.alpha.features.able]
        purpose: Later feature.
        behaviors:
          idle:
            trigger: {statement: A participant starts idling.}
            outcome: {statement: Idling completes.}
    purpose: Later domain.
""",
    )

    assert cli.main(["graph", str(first)]) == 0
    first_output = capsys.readouterr().out
    assert cli.main(["graph", str(second)]) == 0
    assert capsys.readouterr().out == first_output


def test_graph_dot_escaping_is_deterministic_and_utf8_direct() -> None:
    model = copy.deepcopy(_compiled(CANONICAL))
    model["signals"] = [
        {
            "id": 'signal"\\é',
            "meaning": "An artificial serialization test signal.",
            "producer": {"behavior": "unused", "completion": 'completion"\\🧭'},
            "consumers": [{"behavior": "unused", "trigger": 'trigger"\\é'}],
        }
    ]
    model["relationships"] = []
    model["use_case_memberships"] = []

    assert serialize_graph_dot(model) == (
        'digraph pml {\n'
        '  "completion\\"\\\\🧭" [label="completion\\"\\\\🧭"];\n'
        '  "signal\\"\\\\é" [label="signal\\"\\\\é"];\n'
        '  "trigger\\"\\\\é" [label="trigger\\"\\\\é"];\n'
        '  "completion\\"\\\\🧭" -> "signal\\"\\\\é" [kind="causal", style="solid"];\n'
        '  "signal\\"\\\\é" -> "trigger\\"\\\\é" [kind="causal", style="solid"];\n'
        '}\n'
    ).encode("utf-8")


def test_graph_rejects_invalid_and_unsupported_models_without_output_or_writes(
    tmp_path: Path, capsys
) -> None:
    invalid = _write_manifest(
        tmp_path,
        "invalid.pml.yaml",
        """pml: "0.1-draft"
project: {id: invalid, name: Invalid, purpose: Reject this definition.}
domains:
  core:
    purpose: Has an invalid reference.
    features:
      broken:
        purpose: References an unknown actor.
        actors: [missing]
""",
    )
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    assert cli.main(["graph", str(invalid)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[undefined-reference] unknown actor 'missing'" in captured.err
    assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == before

    result = graph_compiled_model({"format": "pml.other", "format_version": 2})
    assert result.exit_code == 1
    assert result.output is None
    assert result.diagnostic == "[unsupported-model] pml.other@2 is not supported"


def test_graph_argparse_rejects_missing_or_unrecognized_arguments(capsys) -> None:
    with pytest.raises(SystemExit) as missing_manifest:
        cli.main(["graph"])

    assert missing_manifest.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "usage: pml graph" in captured.err

    with pytest.raises(SystemExit) as unexpected_flag:
        cli.main(["graph", "not-read.pml.yaml", "--something"])

    assert unexpected_flag.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "unrecognized arguments: --something" in captured.err
