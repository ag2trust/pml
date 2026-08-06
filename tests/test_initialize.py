from pathlib import Path
import shutil

import yaml

import pml.initialize as initialize_module
from pml.cli import main
from pml.initialize import initialize_project


def test_init_creates_only_source_and_product_state(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    product = tmp_path / "mailroom"
    product.mkdir()
    monkeypatch.chdir(product)

    assert main(["init", "--id", "mailroom", "--name", "Mailroom"]) == 0

    source = tmp_path / "mailroom-pml"
    definition = yaml.safe_load((source / "index.pml.yaml").read_text())
    assert definition == {
        "pml": "0.1-draft",
        "project": {"id": "mailroom", "name": "Mailroom"},
    }
    assert yaml.safe_load((source / "bindings.yaml").read_text()) == {
        "pml_bindings": "0.1",
        "bindings": {},
    }
    assert (source / "probes").is_dir()
    assert (product / ".pml").is_dir()
    assert not (product / ".agents").exists()
    assert "PML INITIALIZED" in capsys.readouterr().out


def test_init_does_not_modify_existing_agent_configuration(tmp_path: Path) -> None:
    product = tmp_path / "product"
    agent_file = product / ".agents" / "skills" / "existing" / "SKILL.md"
    agent_file.parent.mkdir(parents=True)
    agent_file.write_text("existing guidance", encoding="utf-8")

    assert initialize_project(product, "product", "Product") is None

    assert agent_file.read_text(encoding="utf-8") == "existing guidance"
    assert not (product / ".agents" / "skills" / "pml").exists()


def test_init_accepts_explicit_external_source(tmp_path: Path) -> None:
    product = tmp_path / "product"
    product.mkdir()
    source = tmp_path / "custom-pml"

    assert initialize_project(product, "product", "Product", source) is None
    assert (source / "index.pml.yaml").is_file()


def test_init_rejects_product_relative_source(tmp_path: Path) -> None:
    product = tmp_path / "product"
    product.mkdir()

    error = initialize_project(product, "product", "Product", Path("policy"))

    assert error == "--source must be outside the implementing product repository"
    assert not (product / "policy").exists()
    assert not (product / ".pml").exists()


def test_init_rejects_every_destination_collision_without_writes(tmp_path: Path) -> None:
    for label, relative_collision in (
        ("source", "../product-pml"),
        ("state", ".pml"),
    ):
        product = tmp_path / label / "product"
        product.mkdir(parents=True)
        collision = (product / relative_collision).resolve()
        collision.mkdir(parents=True)

        error = initialize_project(product, "product", "Product")

        assert error is not None
        assert "destination already exists" in error
        targets = {
            (product.parent / "product-pml").resolve(),
            product / ".pml",
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


def test_init_rejects_invalid_identity_without_writes(tmp_path: Path) -> None:
    product = tmp_path / "product"
    product.mkdir()

    assert initialize_project(product, "Invalid-ID", "Product") is not None
    assert initialize_project(product, "product", "   ") is not None
    assert not (tmp_path / "product-pml").exists()
    assert not (product / ".pml").exists()


def test_init_rejects_overlapping_destinations(tmp_path: Path) -> None:
    product = tmp_path / "product"
    product.mkdir()

    error = initialize_project(product, "product", "Product", Path(".pml"))

    assert error == "initialization destinations must not overlap"
    assert not (product / ".pml").exists()


def test_init_rejects_destination_created_during_commit(tmp_path: Path, monkeypatch) -> None:
    product = tmp_path / "product"
    product.mkdir()
    source = tmp_path / "product-pml"
    original_reserve = initialize_module._reserve_directory

    def reserve_with_concurrent_source(path: Path) -> int:
        if path == source:
            path.mkdir()
            (path / "concurrent.txt").write_text("preserve", encoding="utf-8")
        return original_reserve(path)

    monkeypatch.setattr(
        initialize_module, "_reserve_directory", reserve_with_concurrent_source
    )

    error = initialize_project(product, "product", "Product")

    assert error == f"destination already exists: {source}"
    assert (source / "concurrent.txt").read_text(encoding="utf-8") == "preserve"
    assert not (product / ".pml").exists()


def test_init_does_not_remove_destination_replaced_during_commit(
    tmp_path: Path, monkeypatch
) -> None:
    product = tmp_path / "product"
    product.mkdir()
    source = tmp_path / "product-pml"
    original_matches = initialize_module._matches_directory
    replaced = False

    def replace_source_before_check(path: Path, fd: int) -> bool:
        nonlocal replaced
        if path == source and not replaced:
            replaced = True
            shutil.rmtree(path)
            path.mkdir()
            (path / "concurrent.txt").write_text("preserve", encoding="utf-8")
        return original_matches(path, fd)

    monkeypatch.setattr(
        initialize_module, "_matches_directory", replace_source_before_check
    )

    error = initialize_project(product, "product", "Product")

    assert error == "destination changed during initialization"
    assert (source / "concurrent.txt").read_text(encoding="utf-8") == "preserve"


def test_init_cleans_staging_directory_after_source_write_failure(
    tmp_path: Path, monkeypatch
) -> None:
    product = tmp_path / "product"
    product.mkdir()

    def fail_write(path: Path, document: dict[str, object]) -> None:
        raise OSError("simulated source write failure")

    monkeypatch.setattr(initialize_module, "_write_yaml", fail_write)

    error = initialize_project(product, "product", "Product")

    assert error == "simulated source write failure"
    assert not (tmp_path / "product-pml").exists()
    assert not (product / ".pml").exists()
    assert list(tmp_path.glob(".pml-init-*")) == []
