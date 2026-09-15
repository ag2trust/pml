"""Digest-bound owner review metadata and interactive human review."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import tempfile
from typing import Any, Callable, Mapping, Sequence, TextIO

from jsonschema import Draft202012Validator
import yaml

from pml.diagnostics import Diagnostic
from pml.serialization import canonical_definition_bytes
from pml.validator import INDEX, SUFFIX, UniqueKeyLoader, load_document, validate_document


MAX_REVIEWS_BYTES = 1024 * 1024
ReviewInput = Callable[[str], str]


@dataclass(frozen=True)
class ReviewTarget:
    """One digest-bound reviewable record from the compiled semantic model."""

    id: str
    kind: str
    display_kind: str
    content: dict[str, Any]
    digest: str
    authored_path: tuple[str, ...]


@dataclass
class LoadedReviews:
    """One validated review document and its canonical location."""

    path: Path
    document: dict[str, Any]
    saved_document: dict[str, Any]
    target_ids: frozenset[str]
    saved_target_ids: frozenset[str]
    exists: bool


def reviews_path(manifest: Path) -> Path:
    """Return the adjacent review-metadata path for one definition source."""

    return (
        manifest / "reviews.yaml"
        if manifest.is_dir()
        else manifest.parent / "reviews.yaml"
    )


def _schema() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / "schema" / "pml-reviews.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _path(parts: Sequence[Any]) -> str:
    rendered = ""
    for part in parts:
        if isinstance(part, int):
            rendered += f"[{part}]"
        else:
            rendered += ("." if rendered else "") + str(part)
    return rendered or "$"


def _read_regular_file(path: Path) -> tuple[bytes | None, list[Diagnostic]]:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None, []
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            return None, [
                Diagnostic(
                    str(path),
                    "review-file",
                    "reviews must be a regular non-symbolic file",
                )
            ]
        return None, [Diagnostic(str(path), "review-access", str(exc))]
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            return None, [
                Diagnostic(
                    str(path),
                    "review-file",
                    "reviews must be a regular non-symbolic file",
                )
            ]
        if metadata.st_size > MAX_REVIEWS_BYTES:
            return None, [
                Diagnostic(
                    str(path),
                    "review-size",
                    f"reviews file exceeds {MAX_REVIEWS_BYTES} bytes",
                )
            ]
        chunks: list[bytes] = []
        remaining = MAX_REVIEWS_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > MAX_REVIEWS_BYTES:
            return None, [
                Diagnostic(
                    str(path),
                    "review-size",
                    f"reviews file exceeds {MAX_REVIEWS_BYTES} bytes",
                )
            ]
        return data, []
    except OSError as exc:
        return None, [Diagnostic(str(path), "review-access", str(exc))]
    finally:
        os.close(descriptor)


def _load_review_yaml(path: Path) -> tuple[dict[str, Any] | None, bool, list[Diagnostic]]:
    data, diagnostics = _read_regular_file(path)
    if diagnostics:
        return None, path.exists(), diagnostics
    if data is None:
        return {"pml_reviews": "0.1", "reviews": {}}, False, []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, True, [Diagnostic(str(path), "yaml", str(exc))]
    try:
        document = yaml.load(text, Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        code = getattr(exc, "code", "yaml")
        message = getattr(exc, "message", str(exc))
        mark = getattr(exc, "mark", None)
        location = str(path)
        if mark is not None:
            location += f":{mark.line + 1}:{mark.column + 1}"
        return None, True, [Diagnostic(location, code, message)]
    if not isinstance(document, dict):
        return None, True, [
            Diagnostic(str(path), "structure", "a reviews document must be a mapping")
        ]
    return document, True, []


def _review_target_digest(target_id: str, kind: str, content: Mapping[str, Any]) -> str:
    representation = {"id": target_id, "kind": kind, "content": dict(content)}
    encoded = canonical_definition_bytes(representation)
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def reviews_digest(document: Mapping[str, Any]) -> str:
    """Return the canonical digest of a validated reviews document."""

    encoded = canonical_definition_bytes(document)
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _selected(record: Mapping[str, Any], fields: Sequence[str]) -> dict[str, Any]:
    return {field: record[field] for field in fields if field in record}


def _obligation_authored_path(record: Mapping[str, Any]) -> tuple[str, ...]:
    obligation_id = str(record["id"])
    node = str(record["node"])
    node_parts = tuple(node.split("."))
    kind = record["kind"]
    if kind in {"rule", "use_case", "architecture_constraint"}:
        return tuple(obligation_id.split("."))
    if kind == "conditions":
        return node_parts + ("conditions",)
    if kind in {"completion", "outcome_exclusivity"}:
        return node_parts + (() if kind == "completion" else ("outcome",))
    if kind == "trigger":
        suffix = obligation_id.removeprefix(node + ".trigger")
        return node_parts + ("trigger",) + (("one_of", suffix[1:]) if suffix else ())
    if kind == "outcome":
        suffix = obligation_id.removeprefix(node + ".outcome")
        return node_parts + ("outcome",) + (("one_of", suffix[1:]) if suffix else ())
    if kind == "failure":
        failure_id = obligation_id.removeprefix(node + ".failures.")
        return node_parts + ("failures", failure_id)
    return node_parts


def build_review_targets(model: Mapping[str, Any]) -> tuple[ReviewTarget, ...]:
    """Build the complete deterministic review inventory from compiled model v1."""

    targets: list[ReviewTarget] = []
    produced_signals: dict[str, list[dict[str, Any]]] = {}
    for signal in model.get("signals", []):
        producer = signal["producer"]
        projection = _selected(signal, ("id", "subject", "meaning"))
        projection["completion"] = producer["completion"]
        produced_signals.setdefault(producer["behavior"], []).append(projection)
    for feature in model.get("features", []):
        target_id = feature["path"]
        content = _selected(
            feature,
            (
                "purpose",
                "actors",
                "experience",
                "related_to",
                "architecture",
                "rule_obligations",
                "use_cases",
                "behaviors",
            ),
        )
        targets.append(
            ReviewTarget(
                id=target_id,
                kind="feature",
                display_kind="feature",
                content=content,
                digest=_review_target_digest(target_id, "feature", content),
                authored_path=tuple(target_id.split(".")),
            )
        )
    for behavior in model.get("behaviors", []):
        target_id = behavior["path"]
        content = _selected(
            behavior,
            (
                "conditions",
                "trigger",
                "completion_obligation",
                "outcome",
                "failures",
                "rule_obligations",
                "related_to",
            ),
        )
        if target_id in produced_signals:
            content["produced_signals"] = produced_signals[target_id]
        targets.append(
            ReviewTarget(
                id=target_id,
                kind="behavior",
                display_kind="behavior",
                content=content,
                digest=_review_target_digest(target_id, "behavior", content),
                authored_path=tuple(target_id.split(".")),
            )
        )
    for obligation in model.get("obligations", []):
        target_id = obligation["id"]
        content = _selected(obligation, ("node", "kind", "definition"))
        targets.append(
            ReviewTarget(
                id=target_id,
                kind="obligation",
                display_kind=str(obligation["kind"]),
                content=content,
                digest=_review_target_digest(target_id, "obligation", content),
                authored_path=_obligation_authored_path(obligation),
            )
        )
    return tuple(sorted(targets, key=lambda target: target.id))


def _review_document_diagnostics(
    path: Path,
    document: Mapping[str, Any],
    target_ids: frozenset[str],
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    validator = Draft202012Validator(_schema())
    for error in sorted(
        validator.iter_errors(document), key=lambda item: list(item.absolute_path)
    ):
        diagnostics.append(
            Diagnostic(f"{path}:{_path(error.absolute_path)}", "schema", error.message)
        )
    if diagnostics:
        return diagnostics
    for target_id in document["reviews"]:
        if target_id not in target_ids:
            diagnostics.append(
                Diagnostic(
                    f"{path}:reviews.{target_id}",
                    "undefined-reference",
                    f"unknown review target '{target_id}'",
                )
            )
    return diagnostics


def load_reviews(
    manifest: Path, targets: Sequence[ReviewTarget]
) -> tuple[LoadedReviews | None, list[Diagnostic]]:
    """Load and validate optional adjacent review metadata."""

    path = reviews_path(manifest)
    document, exists, diagnostics = _load_review_yaml(path)
    if document is None:
        return None, diagnostics
    target_ids = frozenset(target.id for target in targets)
    diagnostics.extend(_review_document_diagnostics(path, document, target_ids))
    if diagnostics:
        return None, diagnostics
    return LoadedReviews(
        path=path,
        document=document,
        saved_document=copy.deepcopy(document),
        target_ids=target_ids,
        saved_target_ids=target_ids,
        exists=exists,
    ), []


def review_state(target: ReviewTarget, reviews: Mapping[str, Any]) -> str:
    """Derive one target's current review state."""

    record = reviews.get(target.id)
    if not isinstance(record, Mapping):
        return "pending"
    if record.get("digest") != target.digest:
        return "stale"
    return str(record["status"])


def _ordered_document(document: Mapping[str, Any]) -> dict[str, Any]:
    records: dict[str, Any] = {}
    for target_id in sorted(document["reviews"]):
        record = document["reviews"][target_id]
        ordered = {
            "origin": record["origin"],
            "status": record["status"],
            "digest": record["digest"],
        }
        if "reason" in record:
            ordered["reason"] = record["reason"]
        records[target_id] = ordered
    return {"pml_reviews": "0.1", "reviews": records}


_MISSING = object()


def _merge_review_documents(
    path: Path,
    saved: Mapping[str, Any],
    desired: Mapping[str, Any],
    current: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, list[Diagnostic]]:
    """Three-way merge this session's target-level changes into current metadata."""

    saved_records = saved["reviews"]
    desired_records = desired["reviews"]
    current_records = current["reviews"]
    merged = copy.deepcopy(current)
    merged_records = merged["reviews"]
    diagnostics: list[Diagnostic] = []
    for target_id in sorted(set(saved_records) | set(desired_records)):
        saved_record = saved_records.get(target_id, _MISSING)
        desired_record = desired_records.get(target_id, _MISSING)
        if saved_record == desired_record:
            continue
        current_record = current_records.get(target_id, _MISSING)
        if current_record != saved_record and current_record != desired_record:
            diagnostics.append(
                Diagnostic(
                    f"{path}:reviews.{target_id}",
                    "review-conflict",
                    f"review target '{target_id}' changed after this session loaded it",
                )
            )
            continue
        if desired_record is _MISSING:
            merged_records.pop(target_id, None)
        else:
            merged_records[target_id] = copy.deepcopy(desired_record)
    if diagnostics:
        return None, diagnostics
    return merged, []


def write_reviews(loaded: LoadedReviews) -> list[Diagnostic]:
    """Merge and atomically replace one exact review metadata file."""

    path = loaded.path
    directory_descriptor = -1
    descriptor = -1
    temporary_path: Path | None = None
    try:
        directory_descriptor = os.open(
            path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        )
        fcntl.flock(directory_descriptor, fcntl.LOCK_EX)
        if path.is_symlink():
            return [
                Diagnostic(
                    str(path),
                    "review-file",
                    "reviews must be a regular non-symbolic file",
                )
            ]
        current, _, diagnostics = _load_review_yaml(path)
        if current is None:
            return diagnostics
        diagnostics.extend(
            _review_document_diagnostics(
                path, current, loaded.saved_target_ids | loaded.target_ids
            )
        )
        if diagnostics:
            return diagnostics
        merged, diagnostics = _merge_review_documents(
            path, loaded.saved_document, loaded.document, current
        )
        if merged is None:
            return diagnostics
        for removed_target_id in loaded.saved_target_ids - loaded.target_ids:
            merged["reviews"].pop(removed_target_id, None)
        diagnostics = _review_document_diagnostics(path, merged, loaded.target_ids)
        if diagnostics:
            return diagnostics
        ordered = _ordered_document(merged)
        encoded = yaml.safe_dump(
            ordered, allow_unicode=True, sort_keys=False, default_flow_style=False
        ).encode("utf-8")
        if len(encoded) > MAX_REVIEWS_BYTES:
            return [
                Diagnostic(
                    str(path),
                    "review-size",
                    f"reviews file would exceed {MAX_REVIEWS_BYTES} bytes",
                )
            ]
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".reviews.", suffix=".tmp", dir=path.parent
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
        loaded.document.clear()
        loaded.document.update(ordered)
        loaded.saved_document = copy.deepcopy(ordered)
        loaded.saved_target_ids = loaded.target_ids
        loaded.exists = True
        return []
    except OSError as exc:
        return [Diagnostic(str(path), "review-write", str(exc))]
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
        if directory_descriptor >= 0:
            try:
                fcntl.flock(directory_descriptor, fcntl.LOCK_UN)
            finally:
                os.close(directory_descriptor)


def _definition_snapshot(
    manifest: Path,
) -> tuple[dict[str, Any] | None, tuple[ReviewTarget, ...], list[Diagnostic]]:
    document, diagnostics = load_document(manifest)
    if document is None:
        return None, (), diagnostics
    resolution = validate_document(document)
    diagnostics = list(resolution.diagnostics)
    if diagnostics:
        return None, (), diagnostics
    assert resolution.compiled_model is not None
    return document, build_review_targets(resolution.compiled_model), []


def validate_reviews(manifest: Path) -> list[Diagnostic]:
    """Validate optional review metadata against one valid definition snapshot."""

    _, targets, diagnostics = _definition_snapshot(manifest)
    if diagnostics:
        return diagnostics
    _, diagnostics = load_reviews(manifest, targets)
    return diagnostics


def _mount_path(root: Path, source: Path) -> tuple[str, ...]:
    parts = source.parent.relative_to(root).parts
    name = source.name[: -len(SUFFIX)]
    return parts if name == INDEX else parts + (name,)


def _mapping_has_path(value: Any, parts: Sequence[str]) -> bool:
    current = value
    for part in parts:
        if not isinstance(current, Mapping) or part not in current:
            return False
        current = current[part]
    return True


def _target_sources(manifest: Path, target: ReviewTarget) -> list[Path]:
    if not manifest.is_dir():
        return [manifest]
    sources: list[Path] = []
    for source in sorted(manifest.rglob(f"*{SUFFIX}")):
        mount = _mount_path(manifest, source)
        try:
            fragment = yaml.load(source.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(fragment, Mapping):
            continue
        if target.authored_path[: len(mount)] == mount:
            remainder = target.authored_path[len(mount) :]
            if _mapping_has_path(fragment, remainder):
                sources.append(source)
        elif mount[: len(target.authored_path)] == target.authored_path:
            sources.append(source)
    return sources or [manifest]


def _print_diagnostics(
    diagnostics: Sequence[Diagnostic], output: TextIO, summary: str
) -> None:
    for diagnostic in diagnostics:
        print(diagnostic.format(), file=output)
    print(f"{summary}: {len(diagnostics)} violation(s)", file=output)


def _ask(
    input_fn: ReviewInput, prompt: str, *, normalize: bool = True
) -> str | None:
    try:
        answer = input_fn(prompt).strip()
        return answer.casefold() if normalize else answer
    except (EOFError, KeyboardInterrupt):
        return None


def _origin_for_decision(
    target: ReviewTarget,
    records: Mapping[str, Any],
    default_origin: str | None,
    input_fn: ReviewInput,
    output: TextIO,
) -> str | None:
    record = records.get(target.id)
    if isinstance(record, Mapping) and record.get("digest") == target.digest:
        return str(record["origin"])
    if default_origin is not None:
        return default_origin
    while True:
        answer = _ask(input_fn, "Authoring origin [h]uman, [a]gent, [q]uit: ")
        if answer is None or answer in {"q", "quit"}:
            return None
        if answer in {"h", "human"}:
            return "human"
        if answer in {"a", "agent"}:
            return "agent"
        print("Choose human, agent, or quit.", file=output)


def _render_target(
    target: ReviewTarget,
    state: str,
    position: int,
    total: int,
    sources: Sequence[Path],
    output: TextIO,
) -> None:
    print(file=output)
    print(f"Review {position} of {total} — {state}", file=output)
    print(f"Kind: {target.display_kind}", file=output)
    print(f"ID: {target.id}", file=output)
    for source in sources:
        print(f"Source: {source}", file=output)
    print(file=output)
    rendered = yaml.safe_dump(
        target.content, allow_unicode=True, sort_keys=False, default_flow_style=False
    ).rstrip()
    print(rendered, file=output)
    print(file=output)


def _editor_command(environment: Mapping[str, str]) -> list[str] | None:
    configured = environment.get("VISUAL") or environment.get("EDITOR")
    if not configured:
        return None
    try:
        command = shlex.split(configured)
    except ValueError:
        return None
    return command or None


def _remaining(targets: Sequence[ReviewTarget], records: Mapping[str, Any]) -> int:
    return sum(review_state(target, records) != "approved" for target in targets)


def review_manifest(
    manifest: Path,
    *,
    default_origin: str | None = None,
    input_fn: ReviewInput = input,
    output: TextIO = sys.stdout,
    environment: Mapping[str, str] = os.environ,
) -> int:
    """Run the interactive human review loop for one definition source."""

    if default_origin not in {None, "human", "agent"}:
        print(
            "PML REVIEW UNAVAILABLE: origin must be human or agent",
            file=output,
        )
        return 1

    _, targets, diagnostics = _definition_snapshot(manifest)
    if diagnostics:
        _print_diagnostics(diagnostics, output, "PML REVIEW UNAVAILABLE")
        return 1
    loaded, diagnostics = load_reviews(manifest, targets)
    if loaded is None:
        _print_diagnostics(diagnostics, output, "PML REVIEW UNAVAILABLE")
        return 1

    processed: set[tuple[str, str]] = set()
    counts = {"approved": 0, "rejected": 0, "skipped": 0, "edited": 0}
    quit_requested = False

    while True:
        records = loaded.document["reviews"]
        unresolved = [
            target
            for target in targets
            if review_state(target, records) != "approved"
            and (target.id, target.digest) not in processed
        ]
        if not unresolved or quit_requested:
            break
        target = unresolved[0]
        decided = counts["approved"] + counts["rejected"] + counts["skipped"]
        position = decided + 1
        total = decided + len(unresolved)
        sources = _target_sources(manifest, target)
        _render_target(
            target,
            review_state(target, records),
            position,
            total,
            sources,
            output,
        )
        action = _ask(
            input_fn,
            "[a] approve  [r] reject  [s] skip  [e] edit  [q] quit: ",
        )
        if action is None or action in {"q", "quit"}:
            quit_requested = True
            continue
        if action in {"s", "skip"}:
            counts["skipped"] += 1
            processed.add((target.id, target.digest))
            continue
        if action in {"a", "approve", "r", "reject"}:
            reason: str | None = None
            if action in {"r", "reject"}:
                while True:
                    reason = _ask(
                        input_fn,
                        "Rejection reason (or [q]uit): ",
                        normalize=False,
                    )
                    if reason is None or reason.casefold() in {"q", "quit"}:
                        quit_requested = True
                        break
                    if reason and len(reason) <= 4096 and not any(
                        0xD800 <= ord(character) <= 0xDFFF for character in reason
                    ):
                        break
                    print(
                        "A rejection reason must contain 1 to 4,096 Unicode scalar characters.",
                        file=output,
                    )
                if quit_requested:
                    continue
            origin = _origin_for_decision(
                target, records, default_origin, input_fn, output
            )
            if origin is None:
                quit_requested = True
                continue
            status = "approved" if action in {"a", "approve"} else "rejected"
            record = {"origin": origin, "status": status, "digest": target.digest}
            if reason is not None:
                record["reason"] = reason
            records[target.id] = record
            write_diagnostics = write_reviews(loaded)
            if write_diagnostics:
                _print_diagnostics(write_diagnostics, output, "PML REVIEW NOT SAVED")
                return 1
            counts[status] += 1
            if status == "rejected":
                processed.add((target.id, target.digest))
            continue
        if action in {"e", "edit"}:
            editor = _editor_command(environment)
            if editor is None:
                print(
                    "PML REVIEW EDITOR UNAVAILABLE: set VISUAL or EDITOR to a valid command.",
                    file=output,
                )
                continue
            before = {item.id: item for item in targets}
            try:
                completed = subprocess.run([*editor, *(str(path) for path in sources)])
            except OSError as exc:
                print(f"PML REVIEW EDITOR FAILED: {exc}", file=output)
                return 1
            if completed.returncode != 0:
                print(
                    f"PML REVIEW EDITOR FAILED: exited {completed.returncode}",
                    file=output,
                )
                return 1
            _, updated_targets, edit_diagnostics = _definition_snapshot(manifest)
            if edit_diagnostics:
                _print_diagnostics(
                    edit_diagnostics, output, "PML REVIEW EDIT INVALID"
                )
                return 1
            updated = {item.id: item for item in updated_targets}
            loaded.target_ids = frozenset(updated)
            removed = sorted(set(records).difference(updated))
            for target_id in removed:
                del records[target_id]
                print(
                    f"PML REVIEW REMOVED: obsolete review target {target_id}",
                    file=output,
                )
            changed = [
                item
                for item in updated_targets
                if item.id not in before or before[item.id].digest != item.digest
            ]
            for item in changed:
                records[item.id] = {
                    "origin": "human",
                    "status": "pending",
                    "digest": item.digest,
                }
            if removed or changed:
                write_diagnostics = write_reviews(loaded)
                if write_diagnostics:
                    _print_diagnostics(
                        write_diagnostics, output, "PML REVIEW NOT SAVED"
                    )
                    return 1
            print(
                f"PML REVIEW EDITED: {len(changed)} target(s) changed",
                file=output,
            )
            counts["edited"] += 1
            targets = updated_targets
            continue
        print("Choose approve, reject, skip, edit, or quit.", file=output)

    remaining = _remaining(targets, loaded.document["reviews"])
    print(
        "PML REVIEW SUMMARY: "
        f"approved={counts['approved']} rejected={counts['rejected']} "
        f"skipped={counts['skipped']} edited={counts['edited']} "
        f"remaining={remaining}",
        file=output,
    )
    return 0
