"""Conformance coverage for the read-only compiled-model explain consumer."""

from __future__ import annotations

from pathlib import Path

import pytest

import pml.cli as cli
from pml.explain import build_compiled_model_indexes, explain_compiled_model
from pml.validator import load_document, validate_document


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "tests" / "fixtures" / "compiled_model" / "canonical.pml.yaml"


@pytest.mark.parametrize(
    ("canonical_id", "category"),
    [
        ("project", "Project"),
        ("Alpha", "Vocabulary term"),
        ("ada", "Actor"),
        ("a_record", "Concept"),
        ("architecture.a_store", "Architecture decision"),
        ("domains.a_work", "Domain"),
        ("domains.a_work.features.workspace", "Feature"),
        ("domains.a_work.features.workspace.behaviors.a_start", "Behavior"),
        ("domains.a_work.features.workspace.use_cases.a_flow", "Use case"),
        ("record_ready", "Signal"),
        ("project.rules.a_rule", "Obligation"),
    ],
)
def test_explain_queries_each_requestable_compiled_category(
    canonical_id: str, category: str, capsys
) -> None:
    assert cli.main(["explain", str(CANONICAL), canonical_id]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.startswith(f"{category}\n")
    assert "  Authored:\n" in captured.out
    assert "  Derived identity/structural:\n" in captured.out
    assert "  Derived inverse links:\n" in captured.out


def _collision_manifest(tmp_path: Path) -> Path:
    source = tmp_path / "collisions.pml.yaml"
    source.write_text(
        """pml: "0.1-draft"
project:
  id: explain_test
  name: Explain Test
  purpose: Exercise compiled-model explain lookups.
vocabulary:
  shared_term:
    meaning: A term that collides with flat record identities.
  domains.core.features.f:
    meaning: A term that collides with a feature path.
  domains.core.features.f.behaviors.b.completion:
    meaning: A term that collides with an obligation ID.
actors:
  shared:
    meaning: An actor with a colliding identity.
concepts:
  shared:
    meaning: A concept with a colliding identity.
domains:
  core:
    purpose: Exercise collision and inverse-link lookup.
    features:
      f:
        purpose: The endpoint with only an incoming relationship.
        actors: [shared]
        use_cases:
          u:
            actor: shared
            goal: Use behavior b.
            behaviors: [domains.core.features.f.behaviors.b]
        behaviors:
          b:
            trigger:
              statement: A user starts the behavior.
            outcome:
              statement: The behavior completes.
              signal:
                id: shared
                meaning: A signal with a colliding identity.
      g:
        purpose: The only endpoint that authors the relationship.
        rules:
          observe:
            statement: The product MUST retain the incoming relationship endpoint.
        related_to: [domains.core.features.f]
""",
        encoding="utf-8",
    )
    return source


def _coupling_manifest(tmp_path: Path) -> Path:
    source = tmp_path / "coupling.pml.yaml"
    source.write_text(
        """pml: "0.1-draft"
project:
  id: coupling_test
  name: Coupling Test
  purpose: Exercise derived feature coupling.
domains:
  core:
    purpose: Exercise signals.
    features:
      producer:
        purpose: Produce the signal.
        behaviors:
          produce:
            trigger:
              statement: Production begins.
            outcome:
              statement: Production completes.
              signal:
                id: ready
                meaning: Production is ready.
      consumer:
        purpose: Consume the signal.
        behaviors:
          consume:
            trigger:
              signal: ready
            outcome:
              statement: Consumption completes.
""",
        encoding="utf-8",
    )
    return source


def _compiled(source: Path):  # type: ignore[no-untyped-def]
    document, diagnostics = load_document(source)
    assert document is not None
    assert diagnostics == []
    resolution = validate_document(document)
    assert resolution.diagnostics == ()
    assert resolution.compiled_model is not None
    return resolution.compiled_model


def test_explain_renders_each_flat_identity_collision_in_compiled_category_order(
    tmp_path: Path, capsys
) -> None:
    source = _collision_manifest(tmp_path)

    assert cli.main(["explain", str(source), "shared"]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.index("Actor\n") < captured.out.index("Concept\n")
    assert captured.out.index("Concept\n") < captured.out.index("Signal\n")
    assert captured.out.count("  Authored:\n") == 3
    assert "producer:" in captured.out


def test_explain_surfaces_path_collisions_and_incoming_relationships_read_only(
    tmp_path: Path, capsys
) -> None:
    source = _collision_manifest(tmp_path)
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    assert cli.main(["explain", str(source), "domains.core.features.f"]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.index("Vocabulary term\n") < captured.out.index("Feature\n")
    assert "relationships:" in captured.out
    assert '"declared_by": ["domains.core.features.g"]' in captured.out
    assert "use_case_memberships: []" in captured.out
    assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == before


def test_explain_feature_coupling_section_snapshot(tmp_path: Path, capsys) -> None:
    source = _coupling_manifest(tmp_path)

    assert cli.main(["explain", str(source), "domains.core.features.consumer"]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == """Feature
  Authored:
    id: "consumer"
    purpose: "Consume the signal."
    actors: []
    related_to: []
    architecture: []
  Derived identity/structural:
    path: "domains.core.features.consumer"
    domain: "domains.core"
  Derived inverse links:
    rule_obligations: []
    use_cases: []
    behaviors:
      - "domains.core.features.consumer.behaviors.consume"
    stable_obligations: []
    relationships: []
    use_case_memberships: []
  Derived coupling:
    signals_produced: []
    signals_consumed:
      - {"id": "ready", "producer_feature": "domains.core.features.producer"}
    distinct_producer_feature_count: 1
"""


def test_explain_renders_use_case_and_obligation_and_membership_from_both_sides(
    tmp_path: Path, capsys
) -> None:
    source = _collision_manifest(tmp_path)
    use_case = "domains.core.features.f.use_cases.u"
    behavior = "domains.core.features.f.behaviors.b"

    assert cli.main(["explain", str(source), use_case]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.index("Use case\n") < captured.out.index("Obligation\n")
    assert f'    obligation: "{use_case}"' in captured.out
    assert f'"use_case": "{use_case}", "behavior": "{behavior}"' in captured.out

    assert cli.main(["explain", str(source), behavior]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert f'"use_case": "{use_case}", "behavior": "{behavior}"' in captured.out
    authored = captured.out.split("  Derived identity/structural:", maxsplit=1)[0]
    assert "    path:" not in authored
    assert "completion_obligation" not in authored


def test_explain_renders_vocabulary_and_obligation_collision(tmp_path: Path, capsys) -> None:
    source = _collision_manifest(tmp_path)
    completion = "domains.core.features.f.behaviors.b.completion"

    assert cli.main(["explain", str(source), completion]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.index("Vocabulary term\n") < captured.out.index("Obligation\n")
    assert '    kind: "completion"' in captured.out


def test_compiled_indexes_provide_reverse_and_inverse_lookup_views(tmp_path: Path) -> None:
    model = _compiled(_collision_manifest(tmp_path))
    indexes = build_compiled_model_indexes(model)
    feature = "domains.core.features.f"
    behavior = "domains.core.features.f.behaviors.b"
    use_case = "domains.core.features.f.use_cases.u"

    assert indexes.reverse["shared"] == ("actors", "concepts", "signals")
    assert indexes.reverse[use_case] == ("use_cases", "obligations")
    assert indexes.relationships_for_endpoint(feature)[0]["declared_by"] == [
        "domains.core.features.g"
    ]
    assert indexes.memberships_for_use_case(use_case)[0]["behavior"] == behavior
    assert indexes.memberships_for_behavior(behavior)[0]["use_case"] == use_case
    assert [item["id"] for item in indexes.obligations_for_node(behavior)] == [
        "domains.core.features.f.behaviors.b.completion",
        "domains.core.features.f.behaviors.b.outcome",
        "domains.core.features.f.behaviors.b.trigger",
    ]


def test_explain_unknown_and_invalid_definition_produce_no_stdout(
    tmp_path: Path, capsys
) -> None:
    source = _collision_manifest(tmp_path)

    assert cli.main(["explain", str(source), "domains.missing.features.absent"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "domains.missing.features.absent: [unknown-id] no compiled record matches this ID\n"
    )

    invalid = tmp_path / "invalid.pml.yaml"
    invalid.write_text(
        """pml: "0.1-draft"
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

    assert cli.main(["explain", str(invalid), "missing"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[undefined-reference] unknown actor 'missing'" in captured.err
    assert "PML INVALID: 2 violation(s)" in captured.err


def test_explain_rejects_unsupported_model_before_reading_records() -> None:
    result = explain_compiled_model({"format": "pml.other", "format_version": 2}, "anything")

    assert result.exit_code == 1
    assert result.output is None
    assert result.diagnostic == "[unsupported-model] pml.other@2 is not supported"

    boolean_version = explain_compiled_model(
        {"format": "pml.compiled", "format_version": True}, "anything"
    )
    assert boolean_version.exit_code == 1
    assert boolean_version.output is None
    assert boolean_version.diagnostic == "[unsupported-model] pml.compiled@True is not supported"


def test_explain_argparse_rejects_missing_or_unrecognized_arguments(capsys) -> None:
    with pytest.raises(SystemExit) as missing_id:
        cli.main(["explain", "not-read.pml.yaml"])

    assert missing_id.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "usage: pml explain" in captured.err

    with pytest.raises(SystemExit) as unexpected_flag:
        cli.main(["explain", "not-read.pml.yaml", "id", "--something"])

    assert unexpected_flag.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "unrecognized arguments: --something" in captured.err


def test_explain_preserves_authored_and_derived_classification(capsys) -> None:
    behavior = "domains.a_work.features.workspace.behaviors.a_start"

    assert cli.main(["explain", str(CANONICAL), behavior]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    authored, remaining = captured.out.split("  Derived identity/structural:\n", maxsplit=1)
    structural, inverse = remaining.split("  Derived inverse links:\n", maxsplit=1)
    assert "    path:" not in authored
    assert "    feature:" not in authored
    assert "completion_obligation" not in authored
    assert "    trigger.kind:" in structural
    assert "stable_obligations:" in inverse


def test_explain_renders_completion_transitions_as_authored_data(
    tmp_path: Path, capsys
) -> None:
    source = tmp_path / "completion-transitions.pml.yaml"
    source.write_text(
        """pml: "0.1-draft"
project: {id: transitions, name: Transitions, purpose: Explain completion transitions.}
concepts:
  note:
    meaning: A Note with a lifecycle.
    states: [draft, active]
domains:
  notes:
    purpose: Manage Notes.
    features:
      lifecycle:
        purpose: Move Notes through a lifecycle.
        behaviors:
          direct:
            trigger: {statement: A Member removes an active Note.}
            outcome:
              statement: The active Note ceases to exist.
              transitions: {note: active -> none}
          alternatives:
            trigger: {statement: A Member changes a Note.}
            outcome:
              one_of:
                create:
                  statement: The Note enters draft.
                  transitions: {note: none -> draft}
                activate:
                  statement: The Note becomes active.
                  transitions: {note: draft -> active}
            failures:
              removed:
                statement: The active Note ceases to exist.
                transitions: {note: active -> none}
""",
        encoding="utf-8",
    )
    prefix = "domains.notes.features.lifecycle.behaviors"

    for behavior in (f"{prefix}.direct", f"{prefix}.alternatives"):
        assert cli.main(["explain", str(source), behavior]) == 0
        rendered = capsys.readouterr().out
        authored, remaining = rendered.split(
            "  Derived identity/structural:\n", maxsplit=1
        )
        structural, _ = remaining.split("  Derived inverse links:\n", maxsplit=1)
        assert '"transitions"' in authored
        assert '"transitions"' not in structural

    for obligation in (
        f"{prefix}.direct.outcome",
        f"{prefix}.alternatives.outcome.create",
        f"{prefix}.alternatives.failures.removed",
    ):
        assert cli.main(["explain", str(source), obligation]) == 0
        rendered = capsys.readouterr().out
        authored, remaining = rendered.split(
            "  Derived identity/structural:\n", maxsplit=1
        )
        structural, _ = remaining.split("  Derived inverse links:\n", maxsplit=1)
        assert "definition.transitions" in authored
        assert "definition.transitions" not in structural


def test_explain_lists_referencing_surface_state_on_obligation(capsys) -> None:
    obligation = (
        "domains.a_work.features.workspace.behaviors.a_start.outcome.z_saved"
    )

    assert cli.main(["explain", str(CANONICAL), obligation]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    _, inverse = captured.out.split("  Derived inverse links:\n", maxsplit=1)
    assert (
        "domains.a_work.features.workspace.experience.surfaces.a_workspace.states.z_ready"
        in inverse
    )
