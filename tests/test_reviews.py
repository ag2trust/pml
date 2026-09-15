from __future__ import annotations

from io import StringIO
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

from pml.cli import main
from pml.reviews import (
    MAX_REVIEWS_BYTES,
    ReviewTarget,
    _definition_snapshot,
    build_review_targets,
    load_reviews,
    review_manifest,
    review_state,
    reviews_digest,
    validate_reviews,
    write_reviews,
)
from pml.validator import load_document, validate_document


ROOT = Path(__file__).resolve().parents[1]


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "reviewed-product"
    source.mkdir()
    shutil.copy(ROOT / "examples/reviewed-product/index.pml.yaml", source / "index.pml.yaml")
    return source


def _targets(source: Path):
    document, diagnostics = load_document(source)
    assert document is not None and diagnostics == []
    resolution = validate_document(document)
    assert resolution.diagnostics == ()
    assert resolution.compiled_model is not None
    return build_review_targets(resolution.compiled_model)


def _write_reviews(source: Path, reviews: dict) -> None:
    (source / "reviews.yaml").write_text(
        yaml.safe_dump(
            {"pml_reviews": "0.1", "reviews": reviews},
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_reviewed_product_example_is_valid() -> None:
    assert validate_reviews(ROOT / "examples/reviewed-product") == []


def test_invalid_review_reference_example_is_rejected() -> None:
    diagnostics = validate_reviews(ROOT / "examples/reviewed-product-invalid")

    assert [(item.code, item.message) for item in diagnostics] == [
        (
            "undefined-reference",
            "unknown review target 'domains.notes.features.missing'",
        )
    ]


def test_invalid_review_schema_example_has_closed_schema_diagnostics(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    shutil.copy(ROOT / "examples/invalid-reviews-schema.yaml", source / "reviews.yaml")
    diagnostics = validate_reviews(source)

    assert {item.code for item in diagnostics} == {"schema"}
    messages = {item.message for item in diagnostics}
    assert any("unexpected" in message for message in messages)
    assert any("reason" in message for message in messages)
    assert any("not-a-digest" in message for message in messages)
    assert any("robot" in message for message in messages)


def test_review_inventory_and_digests_are_deterministic() -> None:
    source = ROOT / "examples/reviewed-product"
    first = _targets(source)
    second = _targets(source)

    assert first == second
    assert [target.id for target in first] == sorted(target.id for target in first)
    assert [(target.display_kind, target.digest) for target in first] == [
        ("feature", "sha256:a31b1eba5407c3bcdddb956d92de1607c03c5cdf22c4beb953add8707f3393b1"),
        ("behavior", "sha256:e01077adc2d3331ae77f78de0bf77556bb88966e69a64377534eda9da3589942"),
        ("completion", "sha256:a5ba4467d933cb075bcd7913c643d49bb8498e06dd11d0171a13209c6db25a43"),
        ("outcome", "sha256:8dcec2cea2b1a093401e7ce253ea1e4c86645233d839657d5e91deda12fbcbab"),
        ("trigger", "sha256:905de52b51d413b9808f0954aaae799581a46c7c2291357fbe668e71f53f6205"),
        ("rule", "sha256:7def2ca09fcca717353d1d4a8b1222fe5dba0aa41b93b5321e01d3b752d95c29"),
        ("use_case", "sha256:7ed6a8b0f3eef6f99706c03f47a14e8f346c6e3187069941eee73114d7fdd0da"),
    ]

    loaded, diagnostics = load_reviews(source, first)
    assert loaded is not None and diagnostics == []
    assert reviews_digest(loaded.document) == (
        "sha256:0a0221c8b7163783b12b456db5237a82afc3f4fca52f0177a40ac71a308dbad0"
    )


def test_inline_signal_semantics_participate_in_behavior_review_digest() -> None:
    manifest = ROOT / "examples/behavior-direct-output.pml.yaml"
    document, diagnostics = load_document(manifest)
    assert document is not None and diagnostics == []
    resolution = validate_document(document)
    assert resolution.compiled_model is not None
    before = {
        target.id: target for target in build_review_targets(resolution.compiled_model)
    }
    behavior_id = "domains.email.features.triage.behaviors.importance_decision"

    signal = document["domains"]["email"]["features"]["triage"]["behaviors"][
        "importance_decision"
    ]["outcome"]["signal"]
    signal["meaning"] = "A newly changed Note occurrence."
    updated = validate_document(document)
    assert updated.compiled_model is not None
    after = {
        target.id: target for target in build_review_targets(updated.compiled_model)
    }

    assert before[behavior_id].digest != after[behavior_id].digest
    assert before[behavior_id + ".outcome"].digest == after[behavior_id + ".outcome"].digest


def test_absent_and_stale_reviews_are_valid_derived_states(tmp_path: Path) -> None:
    source = _source(tmp_path)
    targets = _targets(source)
    assert review_state(targets[0], {}) == "pending"
    _write_reviews(
        source,
        {
            targets[0].id: {
                "origin": "agent",
                "status": "approved",
                "digest": "sha256:" + "0" * 64,
            }
        },
    )

    loaded, diagnostics = load_reviews(source, targets)

    assert loaded is not None and diagnostics == []
    assert review_state(targets[0], loaded.document["reviews"]) == "stale"


def test_unknown_review_target_is_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path)
    _write_reviews(
        source,
        {
            "domains.notes.features.missing": {
                "origin": "human",
                "status": "approved",
                "digest": "sha256:" + "0" * 64,
            }
        },
    )

    diagnostics = validate_reviews(source)

    assert [(item.code, item.message) for item in diagnostics] == [
        ("undefined-reference", "unknown review target 'domains.notes.features.missing'")
    ]


@pytest.mark.parametrize(
    "record",
    [
        {"origin": "human", "status": "rejected", "digest": "sha256:" + "0" * 64},
        {
            "origin": "human",
            "status": "approved",
            "digest": "sha256:" + "0" * 64,
            "reason": "Not permitted for an approval.",
        },
        {
            "origin": "human",
            "status": "pending",
            "digest": "sha256:" + "0" * 64,
            "unknown": "value",
        },
    ],
)
def test_review_record_shape_is_closed(tmp_path: Path, record: dict) -> None:
    source = _source(tmp_path)
    _write_reviews(source, {_targets(source)[0].id: record})

    assert any(item.code == "schema" for item in validate_reviews(source))


def test_review_metadata_accepts_more_than_former_capacity_and_id_limits(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    digest = "sha256:" + "0" * 64
    target_ids = [
        f"domains.d.features.f.behaviors.b{index}" for index in range(4097)
    ]
    target_ids.append("domains." + "a" * 2050 + ".features.f")
    targets = tuple(
        ReviewTarget(
            id=target_id,
            kind="behavior",
            display_kind="behavior",
            content={},
            digest=digest,
            authored_path=tuple(target_id.split(".")),
        )
        for target_id in target_ids
    )
    _write_reviews(
        source,
        {
            target_id: {
                "origin": "human",
                "status": "approved",
                "digest": digest,
            }
            for target_id in target_ids
        },
    )

    loaded, diagnostics = load_reviews(source, targets)

    assert loaded is not None and diagnostics == []
    assert len(loaded.document["reviews"]) == 4098


def test_review_file_must_be_bounded_regular_and_non_symbolic(tmp_path: Path) -> None:
    source = _source(tmp_path)
    reviews = source / "reviews.yaml"
    reviews.write_bytes(b"x" * (MAX_REVIEWS_BYTES + 1))
    assert [item.code for item in validate_reviews(source)] == ["review-size"]

    reviews.unlink()
    external = tmp_path / "external.yaml"
    external.write_text("pml_reviews: '0.1'\nreviews: {}\n", encoding="utf-8")
    reviews.symlink_to(external)
    assert [item.code for item in validate_reviews(source)] == ["review-file"]


def test_review_approves_incrementally_and_preserves_current_origin(tmp_path: Path) -> None:
    source = _source(tmp_path)
    target = _targets(source)[0]
    _write_reviews(
        source,
        {
            target.id: {
                "origin": "agent",
                "status": "pending",
                "digest": target.digest,
            }
        },
    )
    answers = iter(["approve", "quit"])
    output = StringIO()

    result = review_manifest(source, input_fn=lambda _: next(answers), output=output)

    assert result == 0
    stored = yaml.safe_load((source / "reviews.yaml").read_text(encoding="utf-8"))
    assert stored["reviews"][target.id] == {
        "origin": "agent",
        "status": "approved",
        "digest": target.digest,
    }
    assert "Review 1 of 7" in output.getvalue()
    assert "Review 2 of 7" in output.getvalue()
    assert "approved=1" in output.getvalue()
    assert "remaining=6" in output.getvalue()


def test_review_prompts_for_origin_and_preserves_rejection_reason(tmp_path: Path) -> None:
    source = _source(tmp_path)
    target = _targets(source)[0]
    answers = iter(["reject", "Needs a clearer observable outcome.", "agent", "quit"])

    result = review_manifest(source, input_fn=lambda _: next(answers), output=StringIO())

    assert result == 0
    stored = yaml.safe_load((source / "reviews.yaml").read_text(encoding="utf-8"))
    assert stored["reviews"][target.id] == {
        "origin": "agent",
        "status": "rejected",
        "digest": target.digest,
        "reason": "Needs a clearer observable outcome.",
    }


def test_review_skip_and_quit_make_no_file(tmp_path: Path) -> None:
    source = _source(tmp_path)
    answers = iter(["skip", "quit"])
    output = StringIO()

    result = review_manifest(source, input_fn=lambda _: next(answers), output=output)

    assert result == 0
    assert not (source / "reviews.yaml").exists()
    assert "skipped=1" in output.getvalue()
    assert "remaining=7" in output.getvalue()


def test_manual_edit_marks_changed_targets_human_pending_and_restarts_queue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path)
    original_target = _targets(source)[0]

    def edit(command: list[str]):
        assert command == ["editor", str(source / "index.pml.yaml")]
        manifest = source / "index.pml.yaml"
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace(
                "Let a Member create a Note.", "Let a Member preserve a new Note."
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("pml.reviews.subprocess.run", edit)
    answers = iter(["edit", "quit"])
    output = StringIO()

    result = review_manifest(
        source,
        input_fn=lambda _: next(answers),
        output=output,
        environment={"EDITOR": "editor"},
    )

    assert result == 0
    updated_target = _targets(source)[0]
    assert updated_target.digest != original_target.digest
    stored = yaml.safe_load((source / "reviews.yaml").read_text(encoding="utf-8"))
    assert stored["reviews"][updated_target.id] == {
        "origin": "human",
        "status": "pending",
        "digest": updated_target.digest,
    }
    assert "edited=1" in output.getvalue()


def test_invalid_manual_edit_leaves_reviews_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path)

    def edit(command: list[str]):
        (source / "index.pml.yaml").write_text("invalid: true\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("pml.reviews.subprocess.run", edit)

    result = review_manifest(
        source,
        input_fn=lambda _: "edit",
        output=StringIO(),
        environment={"EDITOR": "editor"},
    )

    assert result == 1
    assert not (source / "reviews.yaml").exists()


def test_missing_editor_returns_to_current_target(tmp_path: Path) -> None:
    source = _source(tmp_path)
    answers = iter(["edit", "quit"])
    output = StringIO()

    result = review_manifest(
        source, input_fn=lambda _: next(answers), output=output, environment={}
    )

    assert result == 0
    assert "PML REVIEW EDITOR UNAVAILABLE" in output.getvalue()


def test_validate_command_validates_adjacent_reviews(tmp_path: Path, capsys) -> None:
    source = _source(tmp_path)
    _write_reviews(
        source,
        {
            "domains.notes.features.missing": {
                "origin": "human",
                "status": "approved",
                "digest": "sha256:" + "0" * 64,
            }
        },
    )

    assert main(["validate", str(source)]) == 1
    assert "unknown review target 'domains.notes.features.missing'" in capsys.readouterr().out


def test_compile_remains_independent_of_invalid_reviews(tmp_path: Path, capsys) -> None:
    source = _source(tmp_path)
    (source / "reviews.yaml").write_text("invalid: true\n", encoding="utf-8")

    assert main(["compile", str(source), "--json"]) == 0
    assert '"format": "pml.compiled"' in capsys.readouterr().out


def test_atomic_review_write_failure_preserves_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path)
    target = _targets(source)[0]
    _write_reviews(
        source,
        {
            target.id: {
                "origin": "human",
                "status": "pending",
                "digest": target.digest,
            }
        },
    )
    original = (source / "reviews.yaml").read_bytes()
    loaded, diagnostics = load_reviews(source, _targets(source))
    assert loaded is not None and diagnostics == []
    loaded.document["reviews"][target.id]["status"] = "approved"

    def fail_replace(source_path, destination_path):
        raise OSError("simulated replacement failure")

    monkeypatch.setattr("pml.reviews.os.replace", fail_replace)

    diagnostics = write_reviews(loaded)

    assert [item.code for item in diagnostics] == ["review-write"]
    assert (source / "reviews.yaml").read_bytes() == original
    assert list(source.glob(".reviews.*.tmp")) == []


def test_stale_sessions_merge_decisions_for_different_targets(tmp_path: Path) -> None:
    source = _source(tmp_path)
    targets = _targets(source)
    first, first_diagnostics = load_reviews(source, targets)
    second, second_diagnostics = load_reviews(source, targets)
    assert first is not None and first_diagnostics == []
    assert second is not None and second_diagnostics == []
    first_target, second_target = targets[:2]
    first.document["reviews"][first_target.id] = {
        "origin": "human",
        "status": "approved",
        "digest": first_target.digest,
    }
    second.document["reviews"][second_target.id] = {
        "origin": "agent",
        "status": "approved",
        "digest": second_target.digest,
    }

    assert write_reviews(first) == []
    assert write_reviews(second) == []

    stored = yaml.safe_load((source / "reviews.yaml").read_text(encoding="utf-8"))
    assert set(stored["reviews"]) == {first_target.id, second_target.id}
    assert second.document == stored


def test_stale_sessions_reject_conflicting_decisions_for_same_target(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    targets = _targets(source)
    first, first_diagnostics = load_reviews(source, targets)
    second, second_diagnostics = load_reviews(source, targets)
    assert first is not None and first_diagnostics == []
    assert second is not None and second_diagnostics == []
    target = targets[0]
    first.document["reviews"][target.id] = {
        "origin": "human",
        "status": "approved",
        "digest": target.digest,
    }
    second.document["reviews"][target.id] = {
        "origin": "human",
        "status": "rejected",
        "digest": target.digest,
        "reason": "The observable outcome is unclear.",
    }

    assert write_reviews(first) == []
    diagnostics = write_reviews(second)

    assert [item.code for item in diagnostics] == ["review-conflict"]
    stored = yaml.safe_load((source / "reviews.yaml").read_text(encoding="utf-8"))
    assert stored["reviews"][target.id]["status"] == "approved"


def test_oversized_review_write_preserves_existing_file(tmp_path: Path) -> None:
    source = _source(tmp_path)
    targets = _targets(source)
    target = targets[0]
    _write_reviews(
        source,
        {
            target.id: {
                "origin": "human",
                "status": "approved",
                "digest": target.digest,
            }
        },
    )
    original = (source / "reviews.yaml").read_bytes()
    loaded, diagnostics = load_reviews(source, targets)
    assert loaded is not None and diagnostics == []
    added_ids = {
        f"domains.d.features.f.behaviors.large{index}" for index in range(260)
    }
    loaded.target_ids |= added_ids
    for target_id in added_ids:
        loaded.document["reviews"][target_id] = {
            "origin": "human",
            "status": "rejected",
            "digest": "sha256:" + "0" * 64,
            "reason": "x" * 4096,
        }

    diagnostics = write_reviews(loaded)

    assert [item.code for item in diagnostics] == ["review-size"]
    assert (source / "reviews.yaml").read_bytes() == original
    assert list(source.glob(".reviews.*.tmp")) == []


def test_review_rejects_invalid_definition_before_prompting(tmp_path: Path) -> None:
    source = _source(tmp_path)
    (source / "index.pml.yaml").write_text("invalid: true\n", encoding="utf-8")
    prompted = False

    def answer(prompt: str) -> str:
        nonlocal prompted
        prompted = True
        return "quit"

    assert review_manifest(source, input_fn=answer, output=StringIO()) == 1
    assert prompted is False


def test_rejection_reason_length_is_enforced_before_write(tmp_path: Path) -> None:
    source = _source(tmp_path)
    answers = iter(["reject", "x" * 4097, "quit"])
    output = StringIO()

    result = review_manifest(
        source,
        default_origin="human",
        input_fn=lambda _: next(answers),
        output=output,
    )

    assert result == 0
    assert not (source / "reviews.yaml").exists()
    assert "1 to 4,096" in output.getvalue()


def test_review_command_exposes_origin_option(tmp_path: Path, monkeypatch) -> None:
    source = _source(tmp_path)
    captured = {}

    def run(manifest: Path, *, default_origin=None):
        captured.update(manifest=manifest, default_origin=default_origin)
        return 0

    monkeypatch.setattr("pml.cli.review_manifest", run)

    assert main(["review", str(source), "--origin", "agent"]) == 0
    assert captured == {"manifest": source, "default_origin": "agent"}
