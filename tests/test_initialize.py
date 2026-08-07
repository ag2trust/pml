from pathlib import Path
import os
from types import SimpleNamespace

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
    assert list((source / "probes").iterdir()) == []
    assert list((product / ".pml").iterdir()) == []
    assert (product / ".agents/skills/pml/SKILL.md").is_file()
    assert (product / ".agents/skills/pml/agents/openai.yaml").is_file()
    assert "PML INITIALIZED" in capsys.readouterr().out


def test_init_preserves_existing_agent_configuration(tmp_path: Path) -> None:
    product = tmp_path / "product"
    agent_file = product / ".agents/skills/existing/SKILL.md"
    agent_file.parent.mkdir(parents=True)
    agent_file.write_text("existing guidance", encoding="utf-8")

    assert initialize_project(product, "product", "Product") is None

    assert agent_file.read_text(encoding="utf-8") == "existing guidance"
    assert (product / ".agents/skills/pml/SKILL.md").is_file()


def test_init_cli_rejects_source_override(tmp_path: Path, monkeypatch, capsys) -> None:
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
                "elsewhere",
            ]
        )

    assert failure.value.code == 2
    assert "unrecognized arguments: --source" in capsys.readouterr().err
    assert not (tmp_path / "product-pml").exists()


def test_init_rejects_each_destination_collision_without_overwriting(
    tmp_path: Path,
) -> None:
    for label, relative_collision in (
        ("source", "../product-pml"),
        ("state", ".pml"),
        ("skill", ".agents/skills/pml"),
    ):
        product = tmp_path / label / "product"
        product.mkdir(parents=True)
        collision = (product / relative_collision).resolve()
        collision.mkdir(parents=True)
        marker = collision / "preserve.txt"
        marker.write_text("preserve", encoding="utf-8")

        error = initialize_project(product, "product", "Product")

        assert error == f"destination already exists: {collision}"
        assert marker.read_text(encoding="utf-8") == "preserve"


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


def test_init_rejects_invalid_identity_without_writes(tmp_path: Path) -> None:
    product = tmp_path / "product"
    product.mkdir()

    assert initialize_project(product, "Invalid-ID", "Product") is not None
    assert initialize_project(product, "product", "   ") is not None
    assert not (tmp_path / "product-pml").exists()
    assert not (product / ".pml").exists()


def test_init_rejects_destination_created_during_reservation(
    tmp_path: Path, monkeypatch
) -> None:
    product = tmp_path / "product"
    product.mkdir()
    source = tmp_path / "product-pml"
    original_reserve = initialize_module._reserve_directory

    def reserve_with_concurrent_source(parent, path, handles):
        if path == source:
            path.mkdir()
            (path / "concurrent.txt").write_text("preserve", encoding="utf-8")
        return original_reserve(parent, path, handles)

    monkeypatch.setattr(
        initialize_module, "_reserve_directory", reserve_with_concurrent_source
    )

    error = initialize_project(product, "product", "Product")

    assert error == f"destination already exists: {source}"
    assert (source / "concurrent.txt").read_text(encoding="utf-8") == "preserve"


def test_failure_leaves_partial_artifacts_and_never_deletes_concurrent_content(
    tmp_path: Path, monkeypatch
) -> None:
    product = tmp_path / "product"
    product.mkdir()
    source = tmp_path / "product-pml"
    original_write = initialize_module._write_file

    def add_concurrent_content_then_fail(parent, name, content):
        if name == "bindings.yaml":
            concurrent = source / "concurrent/nested"
            concurrent.mkdir(parents=True)
            (concurrent / "preserve.txt").write_text("preserve", encoding="utf-8")
            raise OSError("simulated install failure")
        original_write(parent, name, content)

    monkeypatch.setattr(
        initialize_module, "_write_file", add_concurrent_content_then_fail
    )

    error = initialize_project(product, "product", "Product")

    assert "simulated install failure" in error
    assert "partial initialization artifacts may remain" in error
    assert (source / "index.pml.yaml").is_file()
    assert (source / "concurrent/nested/preserve.txt").read_text() == "preserve"
    assert initialize_project(product, "product", "Product") == (
        f"destination already exists: {source}"
    )


def test_init_rejects_generated_file_replaced_with_symlink(
    tmp_path: Path, monkeypatch
) -> None:
    product = tmp_path / "product"
    product.mkdir()
    source = tmp_path / "product-pml"
    replacement = tmp_path / "replacement"
    replacement.write_text("replacement", encoding="utf-8")
    original_write = initialize_module._write_file

    def replace_index_after_write(parent, name, content):
        entry = original_write(parent, name, content)
        if name == "bindings.yaml":
            index = source / "index.pml.yaml"
            index.unlink()
            index.symlink_to(replacement)
        return entry

    monkeypatch.setattr(initialize_module, "_write_file", replace_index_after_write)

    assert initialize_project(product, "product", "Product") == (
        "destination changed during initialization"
    )
    assert (source / "index.pml.yaml").is_symlink()
    assert replacement.read_text(encoding="utf-8") == "replacement"


def test_repeated_init_does_not_leak_descriptors(tmp_path: Path) -> None:
    descriptor_directory = Path("/dev/fd")
    if not descriptor_directory.is_dir():
        descriptor_directory = Path("/proc/self/fd")
    if not descriptor_directory.is_dir():
        pytest.skip("platform does not expose process file descriptors")
    descriptors_before = len(os.listdir(descriptor_directory))

    for index in range(10):
        product = tmp_path / f"case_{index}/product"
        product.mkdir(parents=True)
        assert initialize_project(product, "product", "Product") is None

    assert len(os.listdir(descriptor_directory)) == descriptors_before


def test_layout_scan_stops_after_first_unexpected_entry(tmp_path: Path, monkeypatch) -> None:
    directory_path = tmp_path / "directory"
    directory_path.mkdir()
    directory = initialize_module._open_directory(directory_path)

    class Entries:
        def __iter__(self):
            yield SimpleNamespace(name="unexpected")
            raise AssertionError("layout scan read beyond the first unexpected entry")

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(initialize_module.os, "scandir", lambda _: Entries())
    try:
        assert not initialize_module._has_exact_entries(directory, {})
    finally:
        os.close(directory.fd)
