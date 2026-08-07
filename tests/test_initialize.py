from pathlib import Path
import errno
import os

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


def test_initialize_project_unmocked_success_path(tmp_path: Path) -> None:
    product = tmp_path / "product"
    product.mkdir()

    assert initialize_project(product, "product", "Product") is None

    assert (tmp_path / "product-pml/index.pml.yaml").is_file()
    assert (tmp_path / "product-pml/probes").is_dir()
    assert (product / ".pml").is_dir()
    assert (product / ".agents/skills/pml/SKILL.md").is_file()


def test_repeated_init_does_not_leak_layout_scan_descriptors(tmp_path: Path) -> None:
    descriptor_directory = Path("/dev/fd")
    if not descriptor_directory.is_dir():
        descriptor_directory = Path("/proc/self/fd")
    if not descriptor_directory.is_dir():
        pytest.skip("platform does not expose process file descriptors")
    descriptors_before = len(os.listdir(descriptor_directory))

    for index in range(10):
        product = tmp_path / f"case_{index}" / "product"
        product.mkdir(parents=True)
        assert initialize_project(product, "product", "Product") is None

    assert len(os.listdir(descriptor_directory)) == descriptors_before


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


def test_init_cleans_new_agent_parent_when_handle_open_fails(
    tmp_path: Path, monkeypatch
) -> None:
    product = tmp_path / "product"
    product.mkdir()
    original_open = initialize_module._open_child_directory
    agent_open_calls = 0

    def fail_open_after_agent_mkdir(parent, name):
        nonlocal agent_open_calls
        if name == ".agents":
            agent_open_calls += 1
            if agent_open_calls == 2:
                raise OSError(errno.EMFILE, "simulated handle exhaustion")
        return original_open(parent, name)

    monkeypatch.setattr(
        initialize_module, "_open_child_directory", fail_open_after_agent_mkdir
    )

    error = initialize_project(product, "product", "Product")

    assert "simulated handle exhaustion" in error
    assert not (product / ".agents").exists()
    assert not (tmp_path / "product-pml").exists()
    assert not (product / ".pml").exists()

    monkeypatch.undo()
    assert initialize_project(product, "product", "Product") is None


def test_init_cleans_reservation_when_handle_open_fails(
    tmp_path: Path, monkeypatch
) -> None:
    product = tmp_path / "product"
    (product / ".agents/skills").mkdir(parents=True)
    source = tmp_path / "product-pml"
    original_open = initialize_module._open_child_directory

    def fail_source_open(parent, name):
        if name == source.name:
            raise OSError(errno.EMFILE, "simulated handle exhaustion")
        return original_open(parent, name)

    monkeypatch.setattr(
        initialize_module, "_open_child_directory", fail_source_open
    )

    error = initialize_project(product, "product", "Product")

    assert "simulated handle exhaustion" in error
    assert not source.exists()
    assert not (product / ".pml").exists()
    assert not (product / ".agents/skills/pml").exists()

    monkeypatch.undo()
    assert initialize_project(product, "product", "Product") is None


def test_cleanup_preserves_file_replaced_after_detached_validation(
    tmp_path: Path, monkeypatch
) -> None:
    product = tmp_path / "product"
    product.mkdir()
    source = tmp_path / "product-pml"
    original_write = initialize_module._write_file
    original_unlink = os.unlink
    replaced = False

    def fail_after_first_source_file(parent, name, content, owned_files):
        if name == "bindings.yaml":
            raise OSError("simulated install failure")
        original_write(parent, name, content, owned_files)

    def replace_file_before_detached_unlink(name, *, dir_fd=None):
        nonlocal replaced
        if (
            isinstance(name, str)
            and name.startswith(".pml-cleanup-")
            and not replaced
        ):
            replaced = True
            replacement_fd = os.open(
                "index.pml.yaml",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=dir_fd,
            )
            try:
                os.write(replacement_fd, b"concurrent")
            finally:
                os.close(replacement_fd)
        return original_unlink(name, dir_fd=dir_fd)

    monkeypatch.setattr(
        initialize_module, "_write_file", fail_after_first_source_file
    )
    monkeypatch.setattr(
        initialize_module.os, "unlink", replace_file_before_detached_unlink
    )

    assert (
        initialize_project(product, "product", "Product")
        == "simulated install failure"
    )
    assert (source / "index.pml.yaml").read_text(encoding="utf-8") == "concurrent"
    assert not (product / ".pml").exists()


def test_cleanup_preserves_directory_replaced_after_detached_validation(
    tmp_path: Path, monkeypatch
) -> None:
    product = tmp_path / "product"
    product.mkdir()
    source = tmp_path / "product-pml"
    original_write = initialize_module._write_file
    original_rmdir = os.rmdir
    replaced = False

    def fail_after_probes_creation(parent, name, content, owned_files):
        if name == "SKILL.md":
            raise OSError("simulated install failure")
        original_write(parent, name, content, owned_files)

    def replace_directory_before_detached_rmdir(name, *, dir_fd=None):
        nonlocal replaced
        if (
            isinstance(name, str)
            and name.startswith(".pml-cleanup-")
            and not (source / "probes").exists()
            and not replaced
        ):
            replaced = True
            os.mkdir("probes", 0o700, dir_fd=dir_fd)
            (source / "probes/concurrent.txt").write_text(
                "preserve", encoding="utf-8"
            )
        return original_rmdir(name, dir_fd=dir_fd)

    monkeypatch.setattr(initialize_module, "_write_file", fail_after_probes_creation)
    monkeypatch.setattr(
        initialize_module.os, "rmdir", replace_directory_before_detached_rmdir
    )

    assert (
        initialize_project(product, "product", "Product")
        == "simulated install failure"
    )
    assert (
        source / "probes/concurrent.txt"
    ).read_text(encoding="utf-8") == "preserve"
    assert not (product / ".pml").exists()
