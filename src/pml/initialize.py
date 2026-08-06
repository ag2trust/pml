"""Deterministic, collision-safe PML project initialization."""

from __future__ import annotations

import os
from pathlib import Path
import re
import stat
import tempfile

import yaml


PROJECT_ID = re.compile(r"^[a-z][a-z0-9_]*$")


def initialize_project(
    product_root: Path,
    project_id: str,
    project_name: str,
    source: Path | None = None,
) -> str | None:
    """Initialize the owner-controlled source and product-local PML state."""
    product_root = product_root.resolve()
    if not PROJECT_ID.fullmatch(project_id):
        return "--id must match ^[a-z][a-z0-9_]*$"
    if not project_name.strip():
        return "--name must not be empty"

    source_path = (
        (product_root.parent / f"{product_root.name}-pml")
        if source is None
        else (product_root / source if not source.is_absolute() else source)
    )
    state_path = product_root / ".pml"
    targets = (source_path, state_path)
    collisions = [str(path) for path in targets if path.exists() or path.is_symlink()]
    if collisions:
        return f"destination already exists: {collisions[0]}"

    resolved_targets = tuple(path.resolve() for path in targets)
    if any(
        left == right or left in right.parents or right in left.parents
        for index, left in enumerate(resolved_targets)
        for right in resolved_targets[index + 1 :]
    ):
        return "initialization destinations must not overlap"
    try:
        resolved_targets[0].relative_to(product_root)
    except ValueError:
        pass
    else:
        return "--source must be outside the implementing product repository"

    staged: list[tuple[Path, int]] = []
    reserved: list[tuple[Path, int]] = []
    initialized = False
    try:
        staged_source = Path(tempfile.mkdtemp(prefix=".pml-init-", dir=source_path.parent))
        staged_source_fd = _open_directory(staged_source)
        staged.append((staged_source, staged_source_fd))
        (staged_source / "probes").mkdir()
        _write_yaml(
            staged_source / "index.pml.yaml",
            {"pml": "0.1-draft", "project": {"id": project_id, "name": project_name}},
        )
        _write_yaml(
            staged_source / "bindings.yaml",
            {"pml_bindings": "0.1", "bindings": {}},
        )
        source_fd = _reserve_directory(source_path)
        reserved.append((source_path, source_fd))
        state_fd = _reserve_directory(state_path)
        reserved.append((state_path, state_fd))

        for name in ("index.pml.yaml", "bindings.yaml"):
            os.link(
                name,
                name,
                src_dir_fd=staged_source_fd,
                dst_dir_fd=source_fd,
                follow_symlinks=False,
            )
            os.unlink(name, dir_fd=staged_source_fd)
        os.mkdir("probes", 0o700, dir_fd=source_fd)
        os.rmdir("probes", dir_fd=staged_source_fd)
        if not all(
            _matches_directory(path, fd)
            for path, fd in reserved
        ):
            return "destination changed during initialization"
        initialized = True
        return None
    except FileExistsError as exc:
        return f"destination already exists: {exc.filename}"
    except OSError as exc:
        return str(exc)
    finally:
        if not initialized:
            for path, fd in reversed(reserved):
                _discard_directory(path, fd)
        for path, fd in staged:
            _discard_directory(path, fd)
        for _, fd in reserved:
            os.close(fd)
        for _, fd in staged:
            os.close(fd)


def _write_yaml(path: Path, document: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def _reserve_directory(path: Path) -> int:
    os.mkdir(path, 0o700)
    return _open_directory(path)


def _open_directory(path: Path) -> int:
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def _matches_directory(path: Path, fd: int) -> bool:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError:
        return False
    expected = os.fstat(fd)
    return metadata.st_dev == expected.st_dev and metadata.st_ino == expected.st_ino


def _discard_directory(path: Path, fd: int) -> None:
    """Empty a pinned directory without traversing its mutable pathname."""

    try:
        _clear_directory(fd)
        if _matches_directory(path, fd):
            os.rmdir(path)
    except OSError:
        pass


def _clear_directory(fd: int) -> None:
    for name in os.listdir(fd):
        metadata = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode):
            child_fd = os.open(
                name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            try:
                _clear_directory(child_fd)
            finally:
                os.close(child_fd)
            os.rmdir(name, dir_fd=fd)
        else:
            os.unlink(name, dir_fd=fd)
