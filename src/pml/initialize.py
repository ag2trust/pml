"""Deterministic, collision-safe PML project initialization."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import os
from pathlib import Path
import re
import secrets

import yaml


PROJECT_ID = re.compile(r"^[a-z][a-z0-9_]*$")
SKILL_FILES = (
    ("SKILL.md",),
    ("agents", "openai.yaml"),
)


@dataclass(frozen=True)
class _Identity:
    device: int
    inode: int


@dataclass
class _Directory:
    path: Path
    fd: int
    identity: _Identity
    parent: _Directory | None = None
    name: str | None = None


@dataclass(frozen=True)
class _OwnedFile:
    parent: _Directory
    name: str
    identity: _Identity


@dataclass(frozen=True)
class _OwnedDirectory:
    parent: _Directory
    name: str
    identity: _Identity


def initialize_project(
    product_root: Path,
    project_id: str,
    project_name: str,
) -> str | None:
    """Initialize the approved sibling source and product-local PML artifacts."""
    product_root = product_root.resolve()
    if not PROJECT_ID.fullmatch(project_id):
        return "--id must match ^[a-z][a-z0-9_]*$"
    if not project_name.strip():
        return "--name must not be empty"

    source_path = product_root.parent / f"{product_root.name}-pml"
    state_path = product_root / ".pml"
    skill_path = product_root / ".agents" / "skills" / "pml"
    targets = (source_path, state_path, skill_path)
    collisions = [str(path) for path in targets if path.exists() or path.is_symlink()]
    if collisions:
        return f"destination already exists: {collisions[0]}"

    definition = yaml.safe_dump(
        {"pml": "0.1-draft", "project": {"id": project_id, "name": project_name}},
        sort_keys=False,
    ).encode()
    bindings = yaml.safe_dump(
        {"pml_bindings": "0.1", "bindings": {}}, sort_keys=False
    ).encode()
    try:
        skill_source = files("pml").joinpath("resources", "skills", "pml")
        skill_content = {
            path: skill_source.joinpath(*path).read_bytes() for path in SKILL_FILES
        }
    except (OSError, TypeError) as exc:
        return f"could not load packaged PML skill: {exc}"

    handles: list[_Directory] = []
    created: list[_OwnedDirectory] = []
    owned_files: list[_OwnedFile] = []
    initialized = False
    try:
        product = _open_directory(product_root)
        handles.append(product)
        source_parent = _open_directory(source_path.parent)
        handles.append(source_parent)

        agents = _ensure_directory(product, ".agents", created, handles)
        skills = _ensure_directory(agents, "skills", created, handles)

        source = _reserve_directory(source_parent, source_path, created, handles)
        state = _reserve_directory(product, state_path, created, handles)
        skill = _reserve_directory(skills, skill_path, created, handles)

        _write_file(source, "index.pml.yaml", definition, owned_files)
        _write_file(source, "bindings.yaml", bindings, owned_files)
        probes = _create_directory(source, "probes", created, handles)

        _write_file(skill, "SKILL.md", skill_content[("SKILL.md",)], owned_files)
        skill_agents = _create_directory(skill, "agents", created, handles)
        _write_file(
            skill_agents,
            "openai.yaml",
            skill_content[("agents", "openai.yaml")],
            owned_files,
        )

        expected_layouts = (
            (source, {"index.pml.yaml", "bindings.yaml", "probes"}),
            (probes, set()),
            (state, set()),
            (skill, {"SKILL.md", "agents"}),
            (skill_agents, {"openai.yaml"}),
        )
        if not all(
            _has_exact_entries(directory, names)
            for directory, names in expected_layouts
        ):
            return "destination changed during initialization"
        if not all(_owned_file_is_attached(item) for item in owned_files):
            return "destination changed during initialization"

        initialized = True
        return None
    except _DestinationExists as exc:
        return f"destination already exists: {exc.path}"
    except OSError as exc:
        return str(exc)
    finally:
        if not initialized:
            for item in reversed(owned_files):
                _quarantine_file(item)
            for directory in reversed(created):
                _quarantine_directory(directory)
        for directory in reversed(handles):
            os.close(directory.fd)


class _DestinationExists(Exception):
    def __init__(self, path: Path):
        self.path = path


def _identity(metadata: os.stat_result) -> _Identity:
    return _Identity(metadata.st_dev, metadata.st_ino)


def _open_directory(path: Path) -> _Directory:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    return _Directory(path, fd, _identity(os.fstat(fd)))


def _open_child_directory(parent: _Directory, name: str) -> _Directory:
    fd = os.open(
        name,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        dir_fd=parent.fd,
    )
    return _Directory(
        parent.path / name,
        fd,
        _identity(os.fstat(fd)),
        parent,
        name,
    )


def _ensure_directory(
    parent: _Directory,
    name: str,
    created: list[_OwnedDirectory],
    handles: list[_Directory],
) -> _Directory:
    try:
        directory = _open_child_directory(parent, name)
    except FileNotFoundError:
        try:
            os.mkdir(name, 0o700, dir_fd=parent.fd)
        except FileExistsError:
            directory = _open_child_directory(parent, name)
        else:
            return _open_created_directory(parent, name, created, handles)
    handles.append(directory)
    return directory


def _reserve_directory(
    parent: _Directory,
    path: Path,
    created: list[_OwnedDirectory],
    handles: list[_Directory],
) -> _Directory:
    try:
        directory = _create_directory(parent, path.name, created, handles)
    except FileExistsError as exc:
        raise _DestinationExists(path) from exc
    return directory


def _create_directory(
    parent: _Directory,
    name: str,
    created: list[_OwnedDirectory],
    handles: list[_Directory],
) -> _Directory:
    os.mkdir(name, 0o700, dir_fd=parent.fd)
    return _open_created_directory(parent, name, created, handles)


def _open_created_directory(
    parent: _Directory,
    name: str,
    created: list[_OwnedDirectory],
    handles: list[_Directory],
) -> _Directory:
    metadata = os.stat(name, dir_fd=parent.fd, follow_symlinks=False)
    owned = _OwnedDirectory(parent, name, _identity(metadata))
    created.append(owned)
    directory = _open_child_directory(parent, name)
    if directory.identity != owned.identity:
        os.close(directory.fd)
        raise OSError("created directory changed during initialization")
    handles.append(directory)
    return directory


def _write_file(
    parent: _Directory,
    name: str,
    content: bytes,
    owned_files: list[_OwnedFile],
) -> None:
    fd = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=parent.fd,
    )
    owned_files.append(_OwnedFile(parent, name, _identity(os.fstat(fd))))
    try:
        output = os.fdopen(fd, "wb")
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    with output:
        output.write(content)


def _directory_is_attached(directory: _Directory) -> bool:
    if directory.parent is None:
        try:
            return (
                _identity(directory.path.stat(follow_symlinks=False))
                == directory.identity
            )
        except OSError:
            return False
    if not _directory_is_attached(directory.parent):
        return False
    try:
        metadata = os.stat(
            directory.name,
            dir_fd=directory.parent.fd,
            follow_symlinks=False,
        )
    except OSError:
        return False
    return _identity(metadata) == directory.identity


def _owned_file_is_attached(item: _OwnedFile) -> bool:
    if not _directory_is_attached(item.parent):
        return False
    try:
        metadata = os.stat(item.name, dir_fd=item.parent.fd, follow_symlinks=False)
    except OSError:
        return False
    return _identity(metadata) == item.identity


def _has_exact_entries(directory: _Directory, expected: set[str]) -> bool:
    """Check a fixed layout without materializing or traversing arbitrary content."""
    if not _directory_is_attached(directory):
        return False
    remaining = set(expected)
    scan_fd = os.dup(directory.fd)
    try:
        with os.scandir(scan_fd) as entries:
            for count, entry in enumerate(entries, start=1):
                if count > len(expected) or entry.name not in remaining:
                    return False
                remaining.remove(entry.name)
        return not remaining
    finally:
        os.close(scan_fd)


def _quarantine_file(item: _OwnedFile) -> None:
    """Detach an unchanged owned file without deleting quarantined content."""
    if _owned_file_is_attached(item):
        _detach_entry(item.parent, item.name)


def _detach_entry(parent: _Directory, name: str) -> str | None:
    """Move an entry to an unpredictable recovery name without deleting it."""
    for _ in range(16):
        detached = f".pml-cleanup-{secrets.token_hex(16)}"
        try:
            os.stat(detached, dir_fd=parent.fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        except OSError:
            return None
        else:
            continue
        try:
            os.rename(
                name,
                detached,
                src_dir_fd=parent.fd,
                dst_dir_fd=parent.fd,
            )
        except OSError:
            return None
        return detached
    return None


def _owned_directory_is_attached(directory: _OwnedDirectory) -> bool:
    """Return whether the public name still identifies the owned directory."""
    if not _directory_is_attached(directory.parent):
        return False
    try:
        metadata = os.stat(
            directory.name,
            dir_fd=directory.parent.fd,
            follow_symlinks=False,
        )
    except OSError:
        return False
    return _identity(metadata) == directory.identity


def _quarantine_directory(directory: _OwnedDirectory) -> None:
    """Detach an unchanged owned directory without deleting quarantined content."""
    if _owned_directory_is_attached(directory):
        _detach_entry(directory.parent, directory.name)
