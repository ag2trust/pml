"""Deterministic, collision-safe PML project initialization."""

from __future__ import annotations

from importlib.resources import files
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
    """Initialize source, product state, and the repository-scoped PML skill."""
    product_root = product_root.resolve()
    if not PROJECT_ID.fullmatch(project_id):
        return "--id must match ^[a-z][a-z0-9_]*$"
    if not project_name.strip():
        return "--name must not be empty"

    source_path = (
        (product_root.parent / f"{product_root.name}-pml")
        if source is None
        else (product_root / source if not source.is_absolute() else source)
    ).resolve()
    state_path = product_root / ".pml"
    skill_path = product_root / ".agents" / "skills" / "pml"
    targets = (source_path, state_path, skill_path)
    if any(
        left == right or left in right.parents or right in left.parents
        for index, left in enumerate(targets)
        for right in targets[index + 1 :]
    ):
        return "initialization destinations must not overlap"
    collisions = [str(path) for path in targets if path.exists() or path.is_symlink()]
    if collisions:
        return f"destination already exists: {collisions[0]}"

    staged: list[tuple[Path, Path]] = []
    committed: list[Path] = []
    created_parents: list[Path] = []
    try:
        staged_source = Path(tempfile.mkdtemp(prefix=".pml-init-", dir=source_path.parent))
        (staged_source / "probes").mkdir()
        _write_yaml(
            staged_source / "index.pml.yaml",
            {"pml": "0.1-draft", "project": {"id": project_id, "name": project_name}},
        )
        _write_yaml(
            staged_source / "bindings.yaml",
            {"pml_bindings": "0.1", "bindings": {}},
        )
        staged.append((staged_source, source_path))

        staged_state = Path(tempfile.mkdtemp(prefix=".pml-state-", dir=product_root))
        staged.append((staged_state, state_path))

        staged_skill = Path(tempfile.mkdtemp(prefix=".pml-skill-", dir=product_root))
        shutil.rmtree(staged_skill)
        staged.append((staged_skill, skill_path))
        shutil.copytree(files("pml").joinpath("resources", "skills", "pml"), staged_skill)

        skill_parent = skill_path.parent
        for parent in (product_root / ".agents", skill_parent):
            if not parent.exists():
                parent.mkdir()
                created_parents.append(parent)

        for temporary, target in staged:
            os.replace(temporary, target)
            committed.append(target)
        return None
    except OSError as exc:
        for target in reversed(committed):
            shutil.rmtree(target, ignore_errors=True)
        return str(exc)
    finally:
        for temporary, _ in staged:
            shutil.rmtree(temporary, ignore_errors=True)
        for parent in reversed(created_parents):
            try:
                parent.rmdir()
            except OSError:
                pass


def _write_yaml(path: Path, document: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
