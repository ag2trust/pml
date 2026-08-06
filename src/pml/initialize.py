"""Deterministic, collision-safe PML project initialization."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
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

    staged: list[Path] = []
    destination_fds: list[int] = []
    try:
        staged_source = Path(tempfile.mkdtemp(prefix=".pml-init-", dir=source_path.parent))
        staged.append(staged_source)
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
        destination_fds.append(source_fd)
        state_fd = _reserve_directory(state_path)
        destination_fds.append(state_fd)

        staged_source_fd = os.open(
            staged_source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        try:
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
        finally:
            os.close(staged_source_fd)
        if not all(
            _matches_directory(path, fd)
            for path, fd in zip(targets, destination_fds, strict=True)
        ):
            return "destination changed during initialization"
        return None
    except FileExistsError as exc:
        return f"destination already exists: {exc.filename}"
    except OSError as exc:
        return str(exc)
    finally:
        for fd in destination_fds:
            os.close(fd)
        for temporary in staged:
            shutil.rmtree(temporary, ignore_errors=True)


def _write_yaml(path: Path, document: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def _reserve_directory(path: Path) -> int:
    os.mkdir(path, 0o700)
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def _matches_directory(path: Path, fd: int) -> bool:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError:
        return False
    expected = os.fstat(fd)
    return metadata.st_dev == expected.st_dev and metadata.st_ino == expected.st_ino
