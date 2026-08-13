"""Validation and fingerprinting for product-local .pml metadata."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any

from jsonschema import Draft202012Validator
import yaml

from pml.formats import FORMAT_CHECKER
from pml.obligations import (
    required_methods,
    verification_coverage,
    verification_plan,
)
from pml.resolver import (
    enumerate_architecture_obligations,
    enumerate_obligations,
    iter_architecture,
    iter_nodes,
)
from pml.validator import Diagnostic, UniqueKeyLoader, _load, _path, load_document


ROOT = Path(__file__).resolve().parents[2]
MAX_ARCHITECTURE_STATE_ENTRIES = 64
# State discovery is also bounded so an untrusted product repository cannot make
# validation retain or diagnose an unbounded number of generated files. This is a
# tooling limit, not a PML language constraint.
MAX_PRODUCT_STATE_ENTRIES = 64
# A product-state tree is untrusted generated output. Bound every directory entry
# visited while discovering state so a tree containing no state files cannot force
# an unbounded recursive traversal. This is a tooling limit, not PML syntax.
MAX_PRODUCT_STATE_SCAN_ENTRIES = 64
# Owner-binding boundary checks inspect product-controlled paths. Cap their
# recursive traversal so a large in-repository directory cannot exhaust the
# validator before an escaping path is found. This is a tooling limit, not PML
# syntax.
MAX_BOUNDARY_SCAN_ENTRIES = 64
# Generated state is tooling output and currently measures well under 1 KiB in the
# conformance examples. One MiB leaves ample room for obligations and evidence while
# bounding memory used before YAML parsing. This is not a PML language constraint.
MAX_STATE_FILE_BYTES = 1024 * 1024
FINGERPRINT_READ_CHUNK_BYTES = 64 * 1024


def state_path_for(repo_root: Path, node_id: str) -> Path:
    """Return the isolated generated-state location for a conformance scope."""

    if node_id.startswith("architecture."):
        return repo_root / ".pml" / "architecture" / f"{node_id.removeprefix('architecture.')}.state.yaml"
    return (repo_root / ".pml" / "state" / Path(*node_id.split("."))).with_suffix(".state.yaml")


def architecture_state_root_diagnostics(repo_root: Path) -> list[Diagnostic]:
    """Reject a generated architecture-state root that escapes its repository."""

    root = repo_root / ".pml" / "architecture"
    if root.is_symlink():
        return [Diagnostic(
            str(root),
            "state-path",
            "architecture state root must not be a symbolic link",
        )]
    if root.exists() and not root.is_dir():
        return [Diagnostic(
            str(root),
            "state-path",
            "architecture state root must be a directory",
        )]
    try:
        root.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return [Diagnostic(
            str(root),
            "outside-repository",
            "architecture state root resolves outside the product repository",
        )]
    return []


def product_state_root_diagnostics(repo_root: Path) -> list[Diagnostic]:
    """Reject a generated product-state root that escapes its repository."""

    root = repo_root / ".pml" / "state"
    if root.is_symlink():
        return [Diagnostic(
            str(root),
            "state-path",
            "product state root must not be a symbolic link",
        )]
    if root.exists() and not root.is_dir():
        return [Diagnostic(
            str(root),
            "state-path",
            "product state root must be a directory",
        )]
    try:
        root.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return [Diagnostic(
            str(root),
            "outside-repository",
            "product state root resolves outside the product repository",
        )]
    return []


def product_state_paths_diagnostics(
    repo_root: Path, state_paths: list[Path]
) -> list[Diagnostic]:
    """Reject product-state paths that escape through a symbolic link."""

    diagnostics = product_state_root_diagnostics(repo_root)
    if diagnostics:
        return diagnostics
    root = repo_root / ".pml" / "state"
    resolved_root = repo_root.resolve()
    reported: set[Path] = set()
    for state_path in state_paths:
        try:
            relative = state_path.relative_to(root)
        except ValueError:
            diagnostics.append(Diagnostic(
                str(state_path),
                "outside-repository",
                "product state path must be below the product state root",
            ))
            continue
        candidate = root
        for part in relative.parts:
            candidate /= part
            if candidate.is_symlink():
                if candidate not in reported:
                    diagnostics.append(Diagnostic(
                        str(candidate),
                        "state-path",
                        "product state path must not contain a symbolic link",
                    ))
                    reported.add(candidate)
                break
        else:
            try:
                state_path.resolve().relative_to(resolved_root)
            except ValueError:
                diagnostics.append(Diagnostic(
                    str(state_path),
                    "outside-repository",
                    "product state path resolves outside the product repository",
                ))
    return diagnostics


def _product_state_parts(repo_root: Path, state_path: Path) -> tuple[str, ...]:
    root = repo_root / ".pml" / "state"
    return state_path.relative_to(root).parts


def _open_product_state_directory(
    repo_root: Path, parts: tuple[str, ...], *, create: bool
) -> int:
    """Open a product-state directory without following any path component."""

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(repo_root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in (".pml", "state", *parts):
            try:
                child_fd = os.open(part, directory_flags, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, dir_fd=fd)
                child_fd = os.open(part, directory_flags, dir_fd=fd)
            os.close(fd)
            fd = child_fd
    except BaseException:
        os.close(fd)
        raise
    return fd


def _product_state_access_diagnostic(path: Path, exc: OSError) -> Diagnostic:
    return Diagnostic(
        str(path),
        "state-path",
        f"could not safely access product state path: {exc}",
    )


def _non_regular_state_diagnostic(path: Path) -> Diagnostic:
    return Diagnostic(
        str(path), "state-path", "generated state must be a regular file"
    )


def _scandir_with_owned_descriptor(directory_fd: int):
    """Start a directory scan that owns a duplicate of ``directory_fd``."""

    scan_fd = os.dup(directory_fd)
    try:
        return os.scandir(scan_fd)
    except BaseException:
        os.close(scan_fd)
        raise


def _unsafe_state_file_diagnostic(path: Path, metadata: os.stat_result) -> Diagnostic | None:
    """Reject state files whose opened inode is unsafe to read or update."""

    if not stat.S_ISREG(metadata.st_mode):
        return _non_regular_state_diagnostic(path)
    if metadata.st_nlink > 1:
        return Diagnostic(
            str(path),
            "state-path",
            "generated state must not have multiple hard links",
        )
    return None


def _open_state_temp_directory(parent_fd: int, state_name: str) -> tuple[str, int]:
    """Create and open a private state directory beneath a pinned parent."""

    for _ in range(16):
        temp_name = f".{state_name}.{secrets.token_hex(16)}.tmp"
        try:
            os.mkdir(temp_name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            continue
        try:
            return temp_name, os.open(
                temp_name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
        except BaseException:
            try:
                os.rmdir(temp_name, dir_fd=parent_fd)
            except OSError:
                pass
            raise
    raise FileExistsError("could not allocate a private generated state directory")


def _write_state(
    parent_fd: int, state_path: Path, state_name: str, encoded: bytes
) -> list[Diagnostic]:
    """Replace state atomically without mutating an existing inode."""

    temp_directory_name: str | None = None
    temp_directory_fd: int | None = None
    temp_fd: int | None = None
    try:
        try:
            state_fd = os.open(
                state_name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=parent_fd,
            )
        except FileNotFoundError:
            pass
        else:
            try:
                diagnostic = _unsafe_state_file_diagnostic(
                    state_path, os.fstat(state_fd)
                )
                if diagnostic:
                    return [diagnostic]
            finally:
                os.close(state_fd)
        temp_directory_name, temp_directory_fd = _open_state_temp_directory(
            parent_fd, state_name
        )
        temp_fd = os.open(
            "state",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=temp_directory_fd,
        )
        diagnostic = _unsafe_state_file_diagnostic(
            state_path, os.fstat(temp_fd)
        )
        if diagnostic:
            return [diagnostic]
        written = 0
        while written < len(encoded):
            written += os.write(temp_fd, encoded[written:])
        temp_metadata = os.fstat(temp_fd)
        os.replace(
            "state",
            state_name,
            src_dir_fd=temp_directory_fd,
            dst_dir_fd=parent_fd,
        )
        installed_fd = os.open(
            state_name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=parent_fd,
        )
        try:
            installed_metadata = os.fstat(installed_fd)
            installed_diagnostic = _unsafe_state_file_diagnostic(
                state_path, installed_metadata
            )
            if installed_diagnostic:
                try:
                    os.unlink(state_name, dir_fd=parent_fd)
                except OSError:
                    pass
                return [installed_diagnostic]
            if (
                installed_metadata.st_dev != temp_metadata.st_dev
                or installed_metadata.st_ino != temp_metadata.st_ino
            ):
                try:
                    os.unlink(state_name, dir_fd=parent_fd)
                except OSError:
                    pass
                return [Diagnostic(
                    str(state_path),
                    "state-path",
                    "generated state replacement source changed before installation",
                )]
        finally:
            os.close(installed_fd)
    except OSError as exc:
        return [_product_state_access_diagnostic(state_path, exc)]
    finally:
        if temp_fd is not None:
            os.close(temp_fd)
        if temp_directory_fd is not None:
            os.close(temp_directory_fd)
        if temp_directory_name is not None:
            try:
                os.rmdir(temp_directory_name, dir_fd=parent_fd)
            except OSError:
                pass
    return []


def _read_product_state(
    repo_root: Path, state_path: Path
) -> tuple[bytes | None, list[Diagnostic]]:
    """Read generated product state through non-following directory handles."""

    try:
        parts = _product_state_parts(repo_root, state_path)
        parent_fd = _open_product_state_directory(
            repo_root, parts[:-1], create=False
        )
    except FileNotFoundError:
        return None, []
    except (OSError, ValueError) as exc:
        return None, [_product_state_access_diagnostic(state_path, exc)]
    try:
        try:
            state_fd = os.open(
                parts[-1],
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=parent_fd,
            )
        except FileNotFoundError:
            return None, []
        except OSError as exc:
            return None, [_product_state_access_diagnostic(state_path, exc)]
    finally:
        os.close(parent_fd)
    try:
        diagnostic = _unsafe_state_file_diagnostic(state_path, os.fstat(state_fd))
        if diagnostic:
            return None, [diagnostic]
        chunks: list[bytes] = []
        remaining = MAX_STATE_FILE_BYTES + 1
        while remaining:
            chunk = os.read(state_fd, min(FINGERPRINT_READ_CHUNK_BYTES, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks), []
    except OSError as exc:
        return None, [_product_state_access_diagnostic(state_path, exc)]
    finally:
        os.close(state_fd)


def write_product_state(
    repo_root: Path, state_path: Path, encoded: bytes
) -> list[Diagnostic]:
    """Write generated product state without following mutable path components."""

    try:
        parts = _product_state_parts(repo_root, state_path)
        parent_fd = _open_product_state_directory(
            repo_root, parts[:-1], create=True
        )
    except (OSError, ValueError) as exc:
        return [_product_state_access_diagnostic(state_path, exc)]
    try:
        return _write_state(parent_fd, state_path, parts[-1], encoded)
    finally:
        os.close(parent_fd)


def _open_architecture_state_directory(repo_root: Path, *, create: bool) -> int:
    """Open the architecture state directory without following mutable links."""

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(repo_root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in (".pml", "architecture"):
            try:
                child_fd = os.open(part, directory_flags, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, dir_fd=fd)
                child_fd = os.open(part, directory_flags, dir_fd=fd)
            os.close(fd)
            fd = child_fd
    except BaseException:
        os.close(fd)
        raise
    return fd


def _read_architecture_state(
    repo_root: Path, state_path: Path
) -> tuple[bytes | None, list[Diagnostic]]:
    try:
        root_fd = _open_architecture_state_directory(repo_root, create=False)
    except FileNotFoundError:
        return None, []
    except OSError as exc:
        return None, [_product_state_access_diagnostic(state_path, exc)]
    try:
        try:
            state_fd = os.open(
                state_path.name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=root_fd,
            )
        except FileNotFoundError:
            return None, []
        except OSError as exc:
            return None, [_product_state_access_diagnostic(state_path, exc)]
    finally:
        os.close(root_fd)
    try:
        diagnostic = _unsafe_state_file_diagnostic(state_path, os.fstat(state_fd))
        if diagnostic:
            return None, [diagnostic]
        chunks: list[bytes] = []
        remaining = MAX_STATE_FILE_BYTES + 1
        while remaining:
            chunk = os.read(state_fd, min(FINGERPRINT_READ_CHUNK_BYTES, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks), []
    except OSError as exc:
        return None, [_product_state_access_diagnostic(state_path, exc)]
    finally:
        os.close(state_fd)


def write_architecture_state(
    repo_root: Path, state_path: Path, encoded: bytes
) -> list[Diagnostic]:
    """Write architecture state through a pinned, non-following directory."""

    try:
        root_fd = _open_architecture_state_directory(repo_root, create=True)
    except OSError as exc:
        return [_product_state_access_diagnostic(state_path, exc)]
    try:
        return _write_state(root_fd, state_path, state_path.name, encoded)
    finally:
        os.close(root_fd)


def _schema(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "schema" / name).read_text())


def canonical_hash(value: Any) -> str:
    """Hash the canonical UTF-8 JSON representation of a validated artifact."""

    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def bindings_digest(bindings: dict[str, Any]) -> str:
    """Return the canonical digest of a validated bindings document."""

    return canonical_hash(bindings)


def _file_fingerprint(path: Path) -> str:
    """Hash a bound file without materializing its complete content in memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(FINGERPRINT_READ_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def input_fingerprint(repo_root: Path, paths: list[str]) -> str:
    """Hash path names and content deterministically, including missing bindings."""

    records: list[tuple[str, str]] = []
    resolved_root = repo_root.resolve()
    for binding in sorted(paths):
        target = repo_root / binding.rstrip("/")
        try:
            target.resolve().relative_to(resolved_root)
        except ValueError:
            records.append((binding, "outside-repository"))
            continue
        if target.is_file():
            records.append((target.relative_to(repo_root).as_posix(), _file_fingerprint(target)))
        elif target.is_dir():
            for child in sorted(item for item in target.rglob("*") if item.is_file()):
                try:
                    relative = child.resolve().relative_to(resolved_root)
                except ValueError:
                    records.append((child.relative_to(repo_root).as_posix(), "outside-repository"))
                    continue
                if relative.parts[:2] == (".pml", "state"):
                    continue
                records.append((relative.as_posix(), _file_fingerprint(child)))
        else:
            records.append((binding, "missing"))
    return canonical_hash(records)


def _bounded_product_state_paths(
    repo_root: Path, max_state_files: int
) -> tuple[list[Path], bool, list[Diagnostic]]:
    """Discover generated product state with bounded recursive traversal."""

    state_root = repo_root / ".pml" / "state"
    try:
        root_fd = _open_product_state_directory(repo_root, (), create=False)
    except FileNotFoundError:
        return [], False, []
    except OSError as exc:
        return [], False, [_product_state_access_diagnostic(state_root, exc)]
    state_paths: list[Path] = []
    pending = [(root_fd, state_root)]
    scanned_entries = 0
    try:
        while pending:
            directory_fd, directory = pending.pop()
            try:
                with _scandir_with_owned_descriptor(directory_fd) as entries:
                    for entry in entries:
                        if scanned_entries == MAX_PRODUCT_STATE_SCAN_ENTRIES:
                            return state_paths, True, []
                        scanned_entries += 1
                        path = directory / entry.name
                        if entry.is_dir(follow_symlinks=False):
                            try:
                                child_fd = os.open(
                                    entry.name,
                                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                    dir_fd=directory_fd,
                                )
                            except OSError as exc:
                                return state_paths, False, [
                                    _product_state_access_diagnostic(path, exc)
                                ]
                            pending.append((child_fd, directory / entry.name))
                        elif entry.name.endswith(".state.yaml"):
                            if len(state_paths) == max_state_files:
                                return state_paths, True, []
                            state_paths.append(directory / entry.name)
            except OSError as exc:
                return state_paths, False, [
                    _product_state_access_diagnostic(directory, exc)
                ]
            finally:
                os.close(directory_fd)
        return state_paths, False, []
    finally:
        for directory_fd, _ in pending:
            os.close(directory_fd)


def _architecture_state_paths(
    repo_root: Path, max_state_files: int
) -> tuple[list[Path], list[Diagnostic]]:
    """Discover flat architecture state through a non-following root handle."""

    root = repo_root / ".pml" / "architecture"
    try:
        root_fd = _open_architecture_state_directory(repo_root, create=False)
    except FileNotFoundError:
        return [], []
    except OSError as exc:
        return [], [_product_state_access_diagnostic(root, exc)]
    diagnostics: list[Diagnostic] = []
    state_paths: list[Path] = []
    try:
        with _scandir_with_owned_descriptor(root_fd) as entries:
            for index, entry in enumerate(entries):
                path = root / entry.name
                if index == MAX_ARCHITECTURE_STATE_ENTRIES:
                    diagnostics.append(Diagnostic(
                        str(root),
                        "state-limit",
                        "architecture state contains too many entries",
                    ))
                    break
                if not entry.is_file(follow_symlinks=False):
                    diagnostics.append(Diagnostic(
                        str(path),
                        "state-path",
                        f"architecture state must be a direct file at {root}",
                    ))
                    continue
                if not entry.name.endswith(".state.yaml"):
                    diagnostics.append(Diagnostic(
                        str(path),
                        "state-path",
                        f"architecture state must be a direct file at {root}",
                    ))
                    continue
                if len(state_paths) == max_state_files:
                    diagnostics.append(Diagnostic(
                        str(root),
                        "state-limit",
                        "architecture state contains more files than approved decisions",
                    ))
                    break
                state_paths.append(path)
    except OSError as exc:
        diagnostics.append(_product_state_access_diagnostic(root, exc))
    finally:
        os.close(root_fd)
    return state_paths, diagnostics


def outside_repository_paths(
    repo_root: Path, paths: list[str]
) -> tuple[list[str], bool]:
    """Return escaped bound paths and whether bounded traversal was exhausted."""

    resolved_root = repo_root.resolve()
    escaped: list[str] = []
    scanned_entries = 0
    for binding in paths:
        target = repo_root / binding.rstrip("/")
        try:
            target.resolve().relative_to(resolved_root)
        except ValueError:
            escaped.append(binding)
            continue
        if target.is_dir():
            pending = [target]
            while pending:
                directory = pending.pop()
                try:
                    with os.scandir(directory) as entries:
                        for entry in entries:
                            if scanned_entries == MAX_BOUNDARY_SCAN_ENTRIES:
                                return escaped, True
                            scanned_entries += 1
                            child = Path(entry.path)
                            try:
                                child.resolve().relative_to(resolved_root)
                            except ValueError:
                                escaped.append(
                                    child.relative_to(repo_root).as_posix()
                                )
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                pending.append(child)
                except OSError:
                    continue
    return escaped, False


def _schema_diagnostics(path: Path, document: dict[str, Any], schema_name: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    validator = Draft202012Validator(
        _schema(schema_name), format_checker=FORMAT_CHECKER
    )
    for error in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path)):
        diagnostics.append(Diagnostic(f"{path}:{_path(error.absolute_path)}", "schema", error.message))
    return diagnostics


def _bindings_semantic_diagnostics(
    path: Path,
    bindings: dict[str, Any],
    definition: dict[str, Any],
    repo_root: Path | None,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    nodes = dict(iter_nodes(definition))
    binding_map = bindings["bindings"]
    decisions = dict(iter_architecture(definition))
    architecture_map = bindings.get("architecture", {})

    for node_id, binding in binding_map.items():
        if node_id not in nodes:
            diagnostics.append(Diagnostic(
                f"{path}:bindings.{node_id}",
                "undefined-reference",
                f"unknown node '{node_id}'",
            ))
            continue
        expected = {
            item.id for item in enumerate_obligations(definition, node_id)
        }
        configured = set(binding.get("verification", {}))
        for obligation_id in sorted(expected.difference(configured)):
            diagnostics.append(Diagnostic(
                f"{path}:bindings.{node_id}.verification",
                "missing-verification-plan",
                f"obligation '{obligation_id}' has no verification plan",
            ))
        for obligation_id in sorted(configured.difference(expected)):
            diagnostics.append(Diagnostic(
                f"{path}:bindings.{node_id}.verification.{obligation_id}",
                "undefined-reference",
                f"unknown obligation '{obligation_id}'",
            ))
        for obligation_id in sorted(expected.intersection(configured)):
            plan = binding["verification"][obligation_id]
            total = sum(verification_coverage(plan).values())
            if abs(total - 1.0) > 1e-9:
                diagnostics.append(Diagnostic(
                    f"{path}:bindings.{node_id}.verification.{obligation_id}",
                    "coverage-total",
                    f"verification coverage must total 1.0, got {total:g}",
                ))

    for node_id in nodes:
        if node_id not in binding_map:
            diagnostics.append(Diagnostic(
                f"{path}:bindings",
                "missing-binding",
                f"node '{node_id}' has no binding",
            ))

    for decision_id, binding in architecture_map.items():
        node_id = f"architecture.{decision_id}"
        if node_id not in decisions:
            diagnostics.append(Diagnostic(
                f"{path}:architecture.{decision_id}",
                "undefined-reference",
                f"unknown architecture decision '{decision_id}'",
            ))
            continue
        expected = {
            item.id
            for item in enumerate_architecture_obligations(definition, node_id)
        }
        configured = set(binding.get("verification", {}))
        for obligation_id in sorted(expected.difference(configured)):
            diagnostics.append(Diagnostic(
                f"{path}:architecture.{decision_id}.verification",
                "missing-verification-plan",
                f"constraint '{obligation_id}' has no verification plan",
            ))
        for obligation_id in sorted(configured.difference(expected)):
            diagnostics.append(Diagnostic(
                f"{path}:architecture.{decision_id}.verification.{obligation_id}",
                "undefined-reference",
                f"unknown architecture constraint '{obligation_id}'",
            ))
        for obligation_id in sorted(expected.intersection(configured)):
            plan = binding["verification"][obligation_id]
            total = sum(verification_coverage(plan).values())
            if abs(total - 1.0) > 1e-9:
                diagnostics.append(Diagnostic(
                    f"{path}:architecture.{decision_id}.verification.{obligation_id}",
                    "coverage-total",
                    f"verification coverage must total 1.0, got {total:g}",
                ))

    for node_id, decision in decisions.items():
        if not decision.get("constraints"):
            continue
        decision_id = node_id.removeprefix("architecture.")
        if decision_id not in architecture_map:
            diagnostics.append(Diagnostic(
                f"{path}:architecture",
                "missing-binding",
                f"architecture decision '{decision_id}' has no binding",
            ))

    if repo_root is not None:
        binding_sections = (
            ("bindings", binding_map),
            ("architecture", architecture_map),
        )
        for section, section_bindings in binding_sections:
            for node_id, binding in section_bindings.items():
                escaped_paths, scan_limit_reached = outside_repository_paths(
                    repo_root, binding["paths"]
                )
                for escaped_path in escaped_paths:
                    diagnostics.append(Diagnostic(
                        f"{path}:{section}.{node_id}.paths",
                        "outside-repository",
                        f"binding '{escaped_path}' resolves outside the product repository",
                    ))
                if scan_limit_reached:
                    diagnostics.append(Diagnostic(
                        f"{path}:{section}.{node_id}.paths",
                        "binding-scan-limit",
                        "binding path contains too many entries to validate safely",
                    ))
    return diagnostics


def load_bindings(
    path: Path,
    definition: dict[str, Any],
    repo_root: Path | None = None,
) -> tuple[dict[str, Any] | None, list[Diagnostic]]:
    """Load bindings only after structural and semantic validation."""

    bindings, diagnostics = _load(path)
    if bindings is None:
        return None, diagnostics
    schema_diagnostics = _schema_diagnostics(
        path, bindings, "pml-bindings.schema.json"
    )
    diagnostics.extend(schema_diagnostics)
    if schema_diagnostics:
        return None, diagnostics
    semantic_diagnostics = _bindings_semantic_diagnostics(
        path, bindings, definition, repo_root
    )
    diagnostics.extend(semantic_diagnostics)
    if semantic_diagnostics:
        return None, diagnostics
    return bindings, diagnostics


@dataclass(frozen=True)
class LockedBindings:
    document: dict[str, Any]
    path: Path
    digest: str


def load_locked_bindings(
    repo_root: Path,
    definition: dict[str, Any],
    definition_source: Path | None = None,
) -> tuple[LockedBindings | None, list[Diagnostic]]:
    """Resolve and validate the exact definition and bindings pinned by the lock."""

    lock_path = repo_root / ".pml" / "pml.lock"
    lock, diagnostics = _load(lock_path)
    if lock is None:
        return None, diagnostics
    lock_errors = _schema_diagnostics(lock_path, lock, "pml-lock.schema.json")
    diagnostics.extend(lock_errors)
    if lock_errors:
        return None, diagnostics

    digest_errors = False
    if lock["definition"]["digest"] != canonical_hash(definition):
        diagnostics.append(Diagnostic(
            f"{lock_path}:definition.digest",
            "definition-digest",
            "lock digest does not match the loaded approved definition",
        ))
        digest_errors = True

    source = Path(lock["definition"]["source"])
    source_path = source if source.is_absolute() else repo_root / source
    source_path = source_path.resolve()
    if not source_path.exists():
        diagnostics.append(Diagnostic(
            f"{lock_path}:definition.source",
            "definition-source",
            "locked definition source does not exist",
        ))
        return None, diagnostics
    if definition_source is None:
        diagnostics.append(Diagnostic(
            f"{lock_path}:definition.source",
            "definition-source",
            "product-state operations require the approved definition source path",
        ))
        return None, diagnostics
    approved_source_path = definition_source.resolve()
    if source_path != approved_source_path:
        diagnostics.append(Diagnostic(
            f"{lock_path}:definition.source",
            "definition-source",
            "locked definition source does not identify the loaded approved definition",
        ))
        return None, diagnostics
    source_definition, source_errors = load_document(approved_source_path)
    diagnostics.extend(source_errors)
    if source_definition is None:
        return None, diagnostics
    if canonical_hash(source_definition) != canonical_hash(definition):
        diagnostics.append(Diagnostic(
            f"{lock_path}:definition.source",
            "definition-source",
            "locked definition source content does not match the loaded approved definition",
        ))
        return None, diagnostics
    bindings_path = (
        source_path / "bindings.yaml"
        if source_path.is_dir()
        else source_path.parent / "bindings.yaml"
    )
    bindings, binding_errors = load_bindings(bindings_path, definition, repo_root)
    diagnostics.extend(binding_errors)
    if bindings is None:
        return None, diagnostics
    if lock["bindings"]["digest"] != bindings_digest(bindings):
        diagnostics.append(Diagnostic(
            f"{lock_path}:bindings.digest",
            "bindings-digest",
            "lock digest does not match the validated approved bindings",
        ))
        digest_errors = True
    if digest_errors:
        return None, diagnostics
    return LockedBindings(
        bindings, bindings_path, bindings_digest(bindings)
    ), diagnostics


def _load_state_encoded(
    path: Path, encoded: bytes
) -> tuple[dict[str, Any] | None, list[Diagnostic]]:
    """Validate bounded generated state bytes against the state schema."""

    if len(encoded) > MAX_STATE_FILE_BYTES:
        return None, [Diagnostic(
            str(path),
            "state-size",
            f"generated state exceeds the {MAX_STATE_FILE_BYTES}-byte tooling limit",
        )]
    try:
        state = yaml.load(encoded.decode("utf-8"), Loader=UniqueKeyLoader)
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        return None, [Diagnostic(str(path), "yaml", str(exc))]
    if not isinstance(state, dict):
        return None, [Diagnostic(
            str(path),
            "structure",
            "a generated state document must be a mapping",
        )]
    diagnostics: list[Diagnostic] = []
    schema_diagnostics = _schema_diagnostics(path, state, "pml-state.schema.json")
    diagnostics.extend(schema_diagnostics)
    if schema_diagnostics:
        return None, diagnostics
    for obligation_id, obligation_state in state["obligations"].items():
        implementation = obligation_state.get("implementation")
        if (
            implementation is not None
            and implementation["status"] != obligation_state["implemented"]
        ):
            diagnostics.append(Diagnostic(
                f"{path}:obligations.{obligation_id}.implemented",
                "implementation-mismatch",
                "implementation status does not match its accepted report record",
            ))
    if diagnostics:
        return None, diagnostics
    return state, diagnostics


def load_state(path: Path) -> tuple[dict[str, Any] | None, list[Diagnostic]]:
    """Load bounded generated state only when it conforms to the state schema."""

    if not path.exists():
        return None, []
    try:
        with path.open("rb") as stream:
            encoded = stream.read(MAX_STATE_FILE_BYTES + 1)
    except OSError as exc:
        return None, [Diagnostic(str(path), "yaml", str(exc))]
    return _load_state_encoded(path, encoded)


def load_product_state(
    repo_root: Path, state_path: Path
) -> tuple[dict[str, Any] | None, list[Diagnostic]]:
    """Load generated product state through non-following path components."""

    encoded, diagnostics = _read_product_state(repo_root, state_path)
    if encoded is None:
        return None, diagnostics
    return _load_state_encoded(state_path, encoded)


def load_architecture_state(
    repo_root: Path, state_path: Path
) -> tuple[dict[str, Any] | None, list[Diagnostic]]:
    """Load architecture state through a pinned, non-following directory."""

    encoded, diagnostics = _read_architecture_state(repo_root, state_path)
    if encoded is None:
        return None, diagnostics
    return _load_state_encoded(state_path, encoded)


def validate_product_state(
    repo_root: Path,
    definition: dict[str, Any],
    locked_bindings: LockedBindings | None = None,
    *,
    definition_source: Path | None = None,
) -> list[Diagnostic]:
    """Validate lock, bindings and state, including current-input fingerprints."""

    diagnostics: list[Diagnostic] = []
    metadata = repo_root / ".pml"
    if locked_bindings is None:
        locked_bindings, errors = load_locked_bindings(
            repo_root, definition, definition_source
        )
        diagnostics.extend(errors)
    if locked_bindings is None:
        return diagnostics
    bindings = locked_bindings.document
    nodes = dict(iter_nodes(definition))
    obligations = {item.id: item for item in enumerate_obligations(definition)}
    binding_map = bindings["bindings"]

    state_root = metadata / "state"
    expected_paths = {
        node_id: state_path_for(repo_root, node_id) for node_id in nodes
    }
    path_errors = product_state_paths_diagnostics(
        repo_root, list(expected_paths.values())
    )
    diagnostics.extend(path_errors)
    if path_errors:
        return diagnostics
    # Allow every approved node and one extra file to be diagnosed, subject to
    # the absolute tooling cap. Discovery also bounds all entries visited, so
    # non-state files cannot make recursive scanning unbounded.
    max_state_files = min(MAX_PRODUCT_STATE_ENTRIES, max(1, len(nodes)) + 1)
    state_paths, state_limit_reached, scan_errors = _bounded_product_state_paths(
        repo_root, max_state_files
    )
    diagnostics.extend(scan_errors)
    if scan_errors:
        return diagnostics
    discovered_paths = set(state_paths)
    if not state_limit_reached:
        for node_id, expected_path in expected_paths.items():
            if expected_path not in discovered_paths:
                diagnostics.append(Diagnostic(str(expected_path), "missing-state", f"node '{node_id}' has no state file"))
    if state_limit_reached:
        diagnostics.append(Diagnostic(
            str(state_root),
            "state-limit",
            "product state contains too many files or entries",
        ))
    path_errors = product_state_paths_diagnostics(repo_root, state_paths)
    diagnostics.extend(path_errors)
    if path_errors:
        return diagnostics
    for state_path in sorted(state_paths):
        state, errors = load_product_state(repo_root, state_path)
        diagnostics.extend(errors)
        if state is None:
            continue
        node_id = state["node"]
        if node_id not in nodes:
            diagnostics.append(Diagnostic(f"{state_path}:node", "undefined-reference", f"unknown node '{node_id}'"))
            continue
        expected_path = expected_paths[node_id]
        if state_path != expected_path:
            diagnostics.append(Diagnostic(str(state_path), "state-path", f"state for '{node_id}' must be at {expected_path}"))
        expected_definition_hash = canonical_hash(nodes[node_id])
        if state["definition_hash"] != expected_definition_hash:
            diagnostics.append(Diagnostic(f"{state_path}:definition_hash", "definition-mismatch", "state does not match the approved node definition"))
        if state["bindings_digest"] != locked_bindings.digest:
            diagnostics.append(Diagnostic(
                f"{state_path}:bindings_digest",
                "bindings-mismatch",
                "state does not match the approved bindings",
            ))
        node_binding = binding_map.get(node_id)
        if node_binding is None:
            diagnostics.append(Diagnostic(f"{state_path}:node", "missing-binding", f"node '{node_id}' has no binding"))
        else:
            current = input_fingerprint(repo_root, node_binding["paths"])
            if state["input_fingerprint"] != current:
                diagnostics.append(Diagnostic(f"{state_path}:input_fingerprint", "sync-required", "state does not cover current bound inputs"))
        declared_related = set(nodes[node_id].get("related_to", []))
        declared_related.update(
            other_id
            for other_id, other in nodes.items()
            if node_id in other.get("related_to", [])
        )
        recorded_related = state.get("related_fingerprints", {})
        for related in sorted(declared_related.difference(recorded_related)):
            diagnostics.append(Diagnostic(f"{state_path}:related_fingerprints", "missing-related", f"state is missing related-node fingerprint '{related}'"))
        for related in sorted(set(recorded_related).difference(declared_related)):
            diagnostics.append(Diagnostic(f"{state_path}:related_fingerprints.{related}", "unknown-related", f"'{related}' is not related to the node"))
        for related in sorted(declared_related.intersection(recorded_related)):
            related_binding = binding_map.get(related)
            if related_binding is not None:
                current_related = input_fingerprint(repo_root, related_binding["paths"])
                if recorded_related[related] != current_related:
                    diagnostics.append(Diagnostic(f"{state_path}:related_fingerprints.{related}", "sync-required", f"related node '{related}' has changed"))
        prefix = node_id + "."
        for obligation_id, obligation_state in state["obligations"].items():
            obligation = obligations.get(obligation_id)
            if obligation is None or not obligation_id.startswith(prefix):
                diagnostics.append(Diagnostic(f"{state_path}:obligations.{obligation_id}", "undefined-reference", f"unknown obligation '{obligation_id}' for node '{node_id}'"))
                continue
            allowed = set(required_methods(verification_plan(bindings, obligation)))
            for method in obligation_state["evidence"]:
                if method not in allowed:
                    diagnostics.append(Diagnostic(f"{state_path}:obligations.{obligation_id}.evidence.{method}", "unexpected-evidence", f"'{method}' is not required by the approved obligation"))
        expected_obligations = {item.id for item in enumerate_obligations(definition, node_id)}
        missing = expected_obligations.difference(state["obligations"])
        for obligation_id in sorted(missing):
            diagnostics.append(Diagnostic(f"{state_path}:obligations", "missing-obligation", f"state is missing '{obligation_id}'"))

    return diagnostics


def validate_architecture_state(
    repo_root: Path,
    definition: dict[str, Any],
    locked_bindings: LockedBindings | None = None,
    *,
    definition_source: Path | None = None,
) -> list[Diagnostic]:
    """Validate independent evidence for owner-approved architecture constraints."""

    diagnostics: list[Diagnostic] = []
    metadata = repo_root / ".pml"
    decisions = dict(iter_architecture(definition))
    constrained_decisions = {
        node_id for node_id, decision in decisions.items() if decision.get("constraints")
    }
    architecture_root = metadata / "architecture"
    canonical_states: dict[str, tuple[Path, dict[str, Any]]] = {}
    root_errors = architecture_state_root_diagnostics(repo_root)
    diagnostics.extend(root_errors)
    if root_errors:
        return diagnostics
    state_paths, state_path_errors = _architecture_state_paths(
        repo_root, max(1, len(decisions)) + 1
    )
    diagnostics.extend(state_path_errors)
    for state_path in sorted(state_paths):
        state, errors = load_architecture_state(repo_root, state_path)
        diagnostics.extend(errors)
        if state is None:
            continue
        node_id = state["node"]
        if node_id not in decisions:
            diagnostics.append(Diagnostic(
                f"{state_path}:node",
                "undefined-reference",
                f"unknown architecture decision '{node_id}'",
            ))
            continue
        expected_path = state_path_for(repo_root, node_id)
        if state_path != expected_path:
            diagnostics.append(Diagnostic(
                str(state_path),
                "state-path",
                f"state for '{node_id}' must be at {expected_path}",
            ))
            continue
        canonical_states[node_id] = (state_path, state)

    for node_id in constrained_decisions:
        state_path = state_path_for(repo_root, node_id)
        if state_path not in state_paths:
            diagnostics.append(Diagnostic(
                str(state_path),
                "missing-state",
                f"architecture decision '{node_id}' has no state file",
            ))

    if locked_bindings is None:
        locked_bindings, errors = load_locked_bindings(
            repo_root, definition, definition_source
        )
        diagnostics.extend(errors)
    if locked_bindings is None:
        return diagnostics
    bindings = locked_bindings.document
    binding_map = bindings.get("architecture", {})
    obligations = {
        item.id: item for item in enumerate_architecture_obligations(definition)
    }
    for node_id, (state_path, state) in canonical_states.items():
        if node_id not in constrained_decisions:
            continue
        decision_id = node_id.removeprefix("architecture.")
        decision = decisions[node_id]
        if state["definition_hash"] != canonical_hash(decision):
            diagnostics.append(Diagnostic(
                f"{state_path}:definition_hash",
                "definition-mismatch",
                "state does not match the approved architecture decision",
            ))
        if state["bindings_digest"] != locked_bindings.digest:
            diagnostics.append(Diagnostic(
                f"{state_path}:bindings_digest",
                "bindings-mismatch",
                "state does not match the approved bindings",
            ))
        current = input_fingerprint(repo_root, binding_map[decision_id]["paths"])
        if state["input_fingerprint"] != current:
            diagnostics.append(Diagnostic(
                f"{state_path}:input_fingerprint",
                "sync-required",
                "state does not cover current bound inputs",
            ))
        expected_obligations = {
            item.id
            for item in enumerate_architecture_obligations(definition, node_id)
        }
        for obligation_id in sorted(
            expected_obligations.difference(state["obligations"])
        ):
            diagnostics.append(Diagnostic(
                f"{state_path}:obligations",
                "missing-obligation",
                f"state is missing '{obligation_id}'",
            ))
        for obligation_id, obligation_state in state["obligations"].items():
            obligation = obligations.get(obligation_id)
            if obligation is None or obligation.node_id != node_id:
                diagnostics.append(Diagnostic(
                    f"{state_path}:obligations.{obligation_id}",
                    "undefined-reference",
                    f"unknown architecture constraint '{obligation_id}'",
                ))
                continue
            allowed = set(required_methods(verification_plan(bindings, obligation)))
            for method in obligation_state["evidence"]:
                if method not in allowed:
                    diagnostics.append(Diagnostic(
                        f"{state_path}:obligations.{obligation_id}.evidence.{method}",
                        "unexpected-evidence",
                        f"'{method}' is not required by the approved constraint",
                    ))
    return diagnostics


def validate_probe_evidence(
    repo_root: Path,
    definition: dict[str, Any],
    probes: dict[str, dict[str, Any]],
    locked_bindings: LockedBindings | None = None,
    *,
    definition_source: Path | None = None,
) -> list[Diagnostic]:
    """Enforce complete, current, passing evidence for every approved probe."""

    diagnostics: list[Diagnostic] = []
    if locked_bindings is None:
        locked_bindings, errors = load_locked_bindings(
            repo_root, definition, definition_source
        )
        diagnostics.extend(errors)
    if locked_bindings is None:
        return diagnostics
    bindings = locked_bindings.document
    probe_by_obligation: dict[str, dict[str, dict[str, Any]]] = {}
    for probe_id, probe in probes.items():
        probe_by_obligation.setdefault(probe["verifies"], {})[probe_id] = probe

    nodes = list(iter_nodes(definition)) + list(iter_architecture(definition))
    product_state_paths = [
        state_path_for(repo_root, node_id)
        for node_id, _ in nodes
        if not node_id.startswith("architecture.")
    ]
    path_errors = product_state_paths_diagnostics(repo_root, product_state_paths)
    diagnostics.extend(path_errors)
    if any(node_id.startswith("architecture.") for node_id, _ in nodes):
        diagnostics.extend(architecture_state_root_diagnostics(repo_root))
    if path_errors:
        return diagnostics
    if diagnostics:
        return diagnostics
    for node_id, _ in nodes:
        state_path = state_path_for(repo_root, node_id)
        if node_id.startswith("architecture."):
            state, state_errors = load_architecture_state(repo_root, state_path)
        else:
            state, state_errors = load_product_state(repo_root, state_path)
        diagnostics.extend(state_errors)
        if state is None:
            continue
        if state.get("bindings_digest") != locked_bindings.digest:
            diagnostics.append(Diagnostic(
                f"{state_path}:bindings_digest",
                "bindings-mismatch",
                "probe evidence does not match the approved bindings",
            ))
            continue
        if node_id.startswith("architecture."):
            paths = bindings.get("architecture", {}).get(node_id.removeprefix("architecture."), {}).get("paths", [])
        else:
            paths = bindings.get("bindings", {}).get(node_id, {}).get("paths", [])
        current_input = input_fingerprint(repo_root, paths)
        enumerator = enumerate_architecture_obligations if node_id.startswith("architecture.") else enumerate_obligations
        for obligation in enumerator(definition, node_id):
            approved = probe_by_obligation.get(obligation.id, {})
            plan = verification_plan(bindings, obligation)
            if "deterministic_probe" not in required_methods(plan):
                continue
            obligation_state = state.get("obligations", {}).get(obligation.id, {})
            evidence = obligation_state.get("evidence", {}).get("deterministic_probe", {})
            configured_probes = set(plan.get("probes", {}))
            for probe_id in sorted(configured_probes.difference(approved)):
                diagnostics.append(Diagnostic(
                    f"{state_path}:obligations.{obligation.id}.evidence.deterministic_probe.{probe_id}",
                    "missing-probe-definition",
                    "verification binding names a probe with no approved definition",
                ))
            for probe_id, probe in approved.items():
                if probe_id not in configured_probes:
                    diagnostics.append(Diagnostic(
                        f"{state_path}:obligations.{obligation.id}.evidence.deterministic_probe.{probe_id}",
                        "unbound-probe",
                        "approved probe has no coverage binding",
                    ))
                    continue
                record = evidence.get(probe_id)
                location = f"{state_path}:obligations.{obligation.id}.evidence.deterministic_probe.{probe_id}"
                if record is None:
                    diagnostics.append(Diagnostic(location, "missing-probe-evidence", "approved probe has no evidence"))
                    continue
                if record["probe"] != probe_id:
                    diagnostics.append(Diagnostic(
                        f"{location}.probe",
                        "probe-mismatch",
                        "evidence record names a different approved probe",
                    ))
                if record["input_fingerprint"] != current_input:
                    diagnostics.append(Diagnostic(location, "stale-probe-evidence", "probe evidence does not cover current bound inputs"))
                if record["probe_fingerprint"] != canonical_hash(probe):
                    diagnostics.append(Diagnostic(location, "probe-mismatch", "evidence does not match the approved probe definition"))
                if record["result"] != "passed":
                    diagnostics.append(Diagnostic(location, "probe-failed", f"approved probe result is {record['result']}"))
            for probe_id in set(evidence).difference(approved):
                diagnostics.append(Diagnostic(
                    f"{state_path}:obligations.{obligation.id}.evidence.deterministic_probe.{probe_id}",
                    "unknown-probe-evidence",
                    "evidence does not identify an approved probe for this obligation",
                ))
    return diagnostics
