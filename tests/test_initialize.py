from pathlib import Path

import pytest
import yaml

import pml.initialize as initialize_module
from pml.cli import main
from pml.initialize import initialize_project


def test_init_creates_source_state_and_repository_skill(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    product = tmp_path / "mailroom"
    product.mkdir()
    monkeypatch.chdir(product)

    assert main(["init", "--id", "mailroom", "--name", "Mailroom"]) == 0

    source = tmp_path / "mailroom-pml"
    assert yaml.safe_load((source / "index.pml.yaml").read_text()) == {
        "pml": "0.1-draft",
        "project": {"id": "mailroom", "name": "Mailroom"},
    }
    assert yaml.safe_load((source / "bindings.yaml").read_text()) == {
        "pml_bindings": "0.1",
        "bindings": {},
    }
    assert (source / "probes").is_dir()
    assert list((source / "probes").iterdir()) == []
    assert list((product / ".pml").iterdir()) == []
    assert (product / ".agents/skills/pml/SKILL.md").is_file()
    assert (product / ".agents/skills/pml/agents/openai.yaml").is_file()
    assert "PML INITIALIZED" in capsys.readouterr().out


def test_init_preserves_existing_agent_configuration(tmp_path: Path) -> None:
    product = tmp_path / "product"
    agent_file = product / ".agents" / "skills" / "existing" / "SKILL.md"
    agent_file.parent.mkdir(parents=True)
    agent_file.write_text("existing guidance", encoding="utf-8")

    assert initialize_project(product, "product", "Product") is None

    assert agent_file.read_text(encoding="utf-8") == "existing guidance"
    assert (product / ".agents/skills/pml/SKILL.md").is_file()


def test_init_cli_rejects_unapproved_source_override(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    product = tmp_path / "product"
    product.mkdir()
    monkeypatch.chdir(product)

    with pytest.raises(SystemExit) as failure:
        main(
            [
                "init",
                "--id",
                "product",
                "--name",
                "Product",
                "--source",
                str(tmp_path / "custom-pml"),
            ]
        )

    assert failure.value.code == 2
    assert "unrecognized arguments: --source" in capsys.readouterr().err
    assert not (tmp_path / "custom-pml").exists()
    assert not (tmp_path / "product-pml").exists()
    assert not (product / ".pml").exists()


def test_init_rejects_every_destination_collision_without_writes(tmp_path: Path) -> None:
    for label, relative_collision in (
        ("source", "../product-pml"),
        ("state", ".pml"),
        ("skill", ".agents/skills/pml"),
    ):
        product = tmp_path / label / "product"
        product.mkdir(parents=True)
        collision = (product / relative_collision).resolve()
        collision.mkdir(parents=True)

        error = initialize_project(product, "product", "Product")

        assert error is not None
        assert "destination already exists" in error
        targets = {
            product.parent / "product-pml",
            product / ".pml",
            product / ".agents/skills/pml",
        }
        assert all(not path.exists() or path == collision for path in targets)


def test_init_rejects_dangling_source_symlink_without_writes(tmp_path: Path) -> None:
    product = tmp_path / "product"
    product.mkdir()
    source = tmp_path / "product-pml"
    external_target = tmp_path / "external-source"
    source.symlink_to(external_target)

    error = initialize_project(product, "product", "Product")

    assert error == f"destination already exists: {source}"
    assert source.is_symlink()
    assert not external_target.exists()
    assert not (product / ".pml").exists()
    assert not (product / ".agents").exists()


def test_init_rejects_symlinked_agent_configuration_boundary(tmp_path: Path) -> None:
    product = tmp_path / "product"
    product.mkdir()
    external_agents = tmp_path / "external-agents"
    external_agents.mkdir()
    (product / ".agents").symlink_to(external_agents, target_is_directory=True)

    error = initialize_project(product, "product", "Product")

    assert error is not None
    assert list(external_agents.iterdir()) == []
    assert not (tmp_path / "product-pml").exists()
    assert not (product / ".pml").exists()


def test_init_rejects_invalid_identity_without_writes(tmp_path: Path) -> None:
    product = tmp_path / "product"
    product.mkdir()

    assert initialize_project(product, "Invalid-ID", "Product") is not None
    assert initialize_project(product, "product", "   ") is not None
    assert not (tmp_path / "product-pml").exists()
    assert not (product / ".pml").exists()
    assert not (product / ".agents").exists()


def test_init_rejects_destination_created_during_reservation(
    tmp_path: Path, monkeypatch
) -> None:
    product = tmp_path / "product"
    product.mkdir()
    source = tmp_path / "product-pml"
    original_reserve = initialize_module._reserve_directory

    def reserve_with_concurrent_source(parent, path, created, handles):
        if path == source:
            path.mkdir()
            (path / "concurrent.txt").write_text("preserve", encoding="utf-8")
        return original_reserve(parent, path, created, handles)

    monkeypatch.setattr(
        initialize_module, "_reserve_directory", reserve_with_concurrent_source
    )

    error = initialize_project(product, "product", "Product")

    assert error == f"destination already exists: {source}"
    assert (source / "concurrent.txt").read_text(encoding="utf-8") == "preserve"
    assert not (product / ".pml").exists()
    assert not (product / ".agents").exists()


def test_init_does_not_remove_destination_replaced_during_initialization(
    tmp_path: Path, monkeypatch
) -> None:
    product = tmp_path / "product"
    product.mkdir()
    source = tmp_path / "product-pml"
    moved_source = tmp_path / "moved-source"
    original_check = initialize_module._has_exact_entries
    replaced = False

    def replace_source_before_check(directory, expected):
        nonlocal replaced
        if directory.path == source and not replaced:
            replaced = True
            source.rename(moved_source)
            source.mkdir()
            (source / "concurrent.txt").write_text("preserve", encoding="utf-8")
        return original_check(directory, expected)

    monkeypatch.setattr(
        initialize_module, "_has_exact_entries", replace_source_before_check
    )

    error = initialize_project(product, "product", "Product")

    assert error == "destination changed during initialization"
    assert (source / "concurrent.txt").read_text(encoding="utf-8") == "preserve"
    assert (moved_source / "index.pml.yaml").is_file()
    assert not (product / ".pml").exists()
    assert not (product / ".agents").exists()


def test_failure_cleanup_removes_only_owned_bounded_entries(
    tmp_path: Path, monkeypatch
) -> None:
    product = tmp_path / "product"
    product.mkdir()
    source = tmp_path / "product-pml"
    original_write = initialize_module._write_file

    def add_concurrent_tree_then_fail(parent, name, content, owned_files):
        if name == "bindings.yaml":
            concurrent = source / "concurrent" / "nested" / "content"
            concurrent.mkdir(parents=True)
            (concurrent / "preserve.txt").write_text("preserve", encoding="utf-8")

            def forbidden_scan(*args, **kwargs):
                raise AssertionError("cleanup must not enumerate reserved content")

            monkeypatch.setattr(initialize_module.os, "scandir", forbidden_scan)
            raise OSError("simulated install failure")
        original_write(parent, name, content, owned_files)

    monkeypatch.setattr(initialize_module, "_write_file", add_concurrent_tree_then_fail)

    error = initialize_project(product, "product", "Product")

    assert error == "simulated install failure"
    assert (source / "concurrent/nested/content/preserve.txt").read_text() == "preserve"
    assert not (source / "index.pml.yaml").exists()
    assert not (product / ".pml").exists()
    assert not (product / ".agents/skills/pml").exists()


def test_failure_cleanup_preserves_concurrently_replaced_owned_file(
    tmp_path: Path, monkeypatch
) -> None:
    product = tmp_path / "product"
    product.mkdir()
    source = tmp_path / "product-pml"
    original_write = initialize_module._write_file

    def replace_file_then_fail(parent, name, content, owned_files):
        if name == "bindings.yaml":
            (source / "index.pml.yaml").unlink()
            (source / "index.pml.yaml").write_text("concurrent", encoding="utf-8")
            raise OSError("simulated install failure")
        original_write(parent, name, content, owned_files)

    monkeypatch.setattr(initialize_module, "_write_file", replace_file_then_fail)

    error = initialize_project(product, "product", "Product")

    assert error == "simulated install failure"
    assert (source / "index.pml.yaml").read_text(encoding="utf-8") == "concurrent"
    assert not (product / ".pml").exists()
    assert not (product / ".agents").exists()


def test_concurrent_content_causes_failure_and_is_not_traversed(
    tmp_path: Path, monkeypatch
) -> None:
    product = tmp_path / "product"
    product.mkdir()
    state = product / ".pml"
    original_write = initialize_module._write_file

    def add_state_content_after_last_write(parent, name, content, owned_files):
        original_write(parent, name, content, owned_files)
        if name == "openai.yaml":
            concurrent = state / "concurrent" / "nested"
            concurrent.mkdir(parents=True)
            (concurrent / "preserve.txt").write_text("preserve", encoding="utf-8")

    monkeypatch.setattr(
        initialize_module, "_write_file", add_state_content_after_last_write
    )

    error = initialize_project(product, "product", "Product")

    assert error == "destination changed during initialization"
    assert (state / "concurrent/nested/preserve.txt").read_text() == "preserve"
    assert not (tmp_path / "product-pml").exists()
    assert not (product / ".agents").exists()


def test_init_cleans_owned_artifacts_after_write_failure(
    tmp_path: Path, monkeypatch
) -> None:
    product = tmp_path / "product"
    product.mkdir()
    original_write = initialize_module._write_file

    def fail_skill_write(parent, name, content, owned_files):
        if name == "SKILL.md":
            raise OSError("simulated skill write failure")
        original_write(parent, name, content, owned_files)

    monkeypatch.setattr(initialize_module, "_write_file", fail_skill_write)

    assert (
        initialize_project(product, "product", "Product")
        == "simulated skill write failure"
    )
    assert not (tmp_path / "product-pml").exists()
    assert not (product / ".pml").exists()
    assert not (product / ".agents").exists()

    monkeypatch.undo()
    assert initialize_project(product, "product", "Product") is None
