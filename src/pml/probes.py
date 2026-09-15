"""Strict loading and semantic validation of approved probe definitions."""

from __future__ import annotations

from dataclasses import dataclass
import errno
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

from jsonschema import Draft202012Validator
import yaml

from pml.resolver import (
    enumerate_architecture_obligations,
    enumerate_obligations,
)
from pml.obligations import (
    verification_plan,
)
from pml.project_state import canonical_hash
from pml.validator import Diagnostic, UniqueKeyLoader, _LoadingError, _path


SCHEMA = Path(__file__).resolve().parents[2] / "schema" / "pml-probe.schema.json"
VARIABLE = re.compile(r"\{([a-z][a-z0-9_]*)\}")
# Probe definitions are untrusted owner-source input. Keep discovery and loading
# bounded before YAML parsing; these are tooling limits, not PML syntax.
MAX_PROBE_DISCOVERY_ENTRIES = 256
MAX_PROBE_FILES = 64
MAX_PROBE_FILE_BYTES = 1024 * 1024


@dataclass
class _ProbeSource:
    """A probe path pinned to an already-open, non-following descriptor."""

    path: Path
    fd: int


def _probe_access_diagnostic(path: Path, exc: OSError) -> Diagnostic:
    return Diagnostic(
        str(path), "probe-path", f"could not safely access probe path: {exc}"
    )


def _probe_symlink_diagnostic(path: Path) -> Diagnostic:
    return Diagnostic(
        str(path), "probe-path", "probe paths must not be symbolic links"
    )


def _non_regular_probe_diagnostic(path: Path) -> Diagnostic:
    return Diagnostic(
        str(path), "probe-path", "probe definitions must be regular files"
    )


def _close_probe_sources(sources: list[_ProbeSource]) -> None:
    for source in sources:
        os.close(source.fd)


def _scandir_with_owned_descriptor(directory_fd: int):
    """Start a directory scan that owns a duplicate of ``directory_fd``."""

    scan_fd = os.dup(directory_fd)
    try:
        return os.scandir(scan_fd)
    except BaseException:
        os.close(scan_fd)
        raise


def _open_probe_file(
    parent_fd: int, name: str, path: Path
) -> tuple[_ProbeSource | None, list[Diagnostic]]:
    """Open one regular probe file relative to a pinned parent directory."""

    try:
        fd = os.open(
            name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd
        )
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            return None, [_probe_symlink_diagnostic(path)]
        return None, [_probe_access_diagnostic(path, exc)]
    source: _ProbeSource | None = None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None, [_non_regular_probe_diagnostic(path)]
        source = _ProbeSource(path, fd)
        return source, []
    except OSError as exc:
        return None, [_probe_access_diagnostic(path, exc)]
    finally:
        # Ownership transfers only when the returned source retains the descriptor.
        if source is None:
            os.close(fd)


def _discover_probe_sources(path: Path) -> tuple[list[_ProbeSource], list[Diagnostic]]:
    """Find probe files through non-following descriptors with bounded traversal."""

    try:
        root_fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            return [], [_probe_symlink_diagnostic(path)]
        return [], [_probe_access_diagnostic(path, exc)]

    try:
        root_metadata = os.fstat(root_fd)
    except OSError as exc:
        os.close(root_fd)
        return [], [_probe_access_diagnostic(path, exc)]

    if stat.S_ISREG(root_metadata.st_mode):
        return [_ProbeSource(path, root_fd)], []
    if not stat.S_ISDIR(root_metadata.st_mode):
        os.close(root_fd)
        return [], [_non_regular_probe_diagnostic(path)]

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    sources: list[_ProbeSource] = []
    pending: list[tuple[tuple[str, ...], int, Path]] = [((), root_fd, path)]
    scanned_entries = 0
    try:
        while pending:
            pending.sort(reverse=True)
            relative, directory_fd, directory = pending.pop()
            try:
                names: list[str] = []
                with _scandir_with_owned_descriptor(directory_fd) as entries:
                    for entry in entries:
                        if scanned_entries == MAX_PROBE_DISCOVERY_ENTRIES:
                            _close_probe_sources(sources)
                            return [], [Diagnostic(
                                str(path),
                                "probe-limit",
                                f"probe discovery exceeds the {MAX_PROBE_DISCOVERY_ENTRIES}-entry tooling limit",
                            )]
                        scanned_entries += 1
                        names.append(entry.name)
                for name in sorted(names):
                    child_path = directory / name
                    try:
                        metadata = os.stat(
                            name, dir_fd=directory_fd, follow_symlinks=False
                        )
                    except OSError as exc:
                        _close_probe_sources(sources)
                        return [], [_probe_access_diagnostic(child_path, exc)]
                    if stat.S_ISLNK(metadata.st_mode):
                        _close_probe_sources(sources)
                        return [], [_probe_symlink_diagnostic(child_path)]
                    if stat.S_ISDIR(metadata.st_mode):
                        try:
                            child_fd = os.open(name, directory_flags, dir_fd=directory_fd)
                        except OSError as exc:
                            _close_probe_sources(sources)
                            if exc.errno == errno.ELOOP:
                                return [], [_probe_symlink_diagnostic(child_path)]
                            return [], [_probe_access_diagnostic(child_path, exc)]
                        pending.append((relative + (name,), child_fd, child_path))
                        continue
                    if not name.endswith(".probe.yaml"):
                        continue
                    if not stat.S_ISREG(metadata.st_mode):
                        _close_probe_sources(sources)
                        return [], [_non_regular_probe_diagnostic(child_path)]
                    if len(sources) == MAX_PROBE_FILES:
                        _close_probe_sources(sources)
                        return [], [Diagnostic(
                            str(path),
                            "probe-limit",
                            f"probe discovery exceeds the {MAX_PROBE_FILES}-file tooling limit",
                        )]
                    source, diagnostics = _open_probe_file(
                        directory_fd, name, child_path
                    )
                    if diagnostics:
                        _close_probe_sources(sources)
                        return [], diagnostics
                    assert source is not None
                    sources.append(source)
            except OSError as exc:
                _close_probe_sources(sources)
                return [], [_probe_access_diagnostic(directory, exc)]
            finally:
                os.close(directory_fd)
        return sorted(sources, key=lambda source: str(source.path)), []
    finally:
        for _, directory_fd, _ in pending:
            os.close(directory_fd)


def _read_probe_source(source: _ProbeSource) -> tuple[bytes | None, list[Diagnostic]]:
    """Read one pinned probe only when its regular-file size is within the bound."""

    try:
        metadata = os.fstat(source.fd)
        diagnostic = _probe_file_metadata_diagnostic(source.path, metadata)
        if diagnostic:
            return None, [diagnostic]
        chunks: list[bytes] = []
        remaining = MAX_PROBE_FILE_BYTES + 1
        while remaining:
            chunk = os.read(source.fd, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        encoded = b"".join(chunks)
        if len(encoded) > MAX_PROBE_FILE_BYTES:
            return None, [Diagnostic(
                str(source.path),
                "probe-size",
                f"probe file exceeds the {MAX_PROBE_FILE_BYTES}-byte tooling limit",
            )]
        return encoded, []
    except OSError as exc:
        return None, [_probe_access_diagnostic(source.path, exc)]


def _probe_file_metadata_diagnostic(
    path: Path, metadata: os.stat_result
) -> Diagnostic | None:
    if not stat.S_ISREG(metadata.st_mode):
        return _non_regular_probe_diagnostic(path)
    if metadata.st_size > MAX_PROBE_FILE_BYTES:
        return Diagnostic(
            str(path),
            "probe-size",
            f"probe file exceeds the {MAX_PROBE_FILE_BYTES}-byte tooling limit",
        )
    return None


def _probe_file_preflight(source: _ProbeSource) -> list[Diagnostic]:
    """Check every discovered file's stable metadata before YAML loading starts."""

    try:
        diagnostic = _probe_file_metadata_diagnostic(source.path, os.fstat(source.fd))
        return [diagnostic] if diagnostic else []
    except OSError as exc:
        return [_probe_access_diagnostic(source.path, exc)]


def _load_probe_encoded(
    path: Path, encoded: bytes
) -> tuple[dict[str, Any] | None, list[Diagnostic]]:
    """Load bounded, descriptor-pinned probe bytes with the standard YAML rules."""

    try:
        document = yaml.load(encoded.decode("utf-8"), Loader=UniqueKeyLoader)
    except _LoadingError as exc:
        location = f"{path}:{exc.mark.line + 1}:{exc.mark.column + 1}"
        return None, [Diagnostic(location, exc.code, exc.message)]
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        return None, [Diagnostic(str(path), "yaml", str(exc))]
    if not isinstance(document, dict):
        return None, [Diagnostic(
            str(path), "structure", "a PML document must be a mapping"
        )]
    return document, []


def probe_fingerprint(probe: dict[str, Any]) -> str:
    """Return the canonical fingerprint recorded with probe evidence."""

    return canonical_hash(probe)


def load_probes(
    path: Path,
    definition: dict[str, Any],
    bindings: dict[str, Any] | None = None,
) -> tuple[dict[str, dict[str, Any]], list[Diagnostic]]:
    """Load owner-approved probes and validate their definition bindings."""

    sources, discovery_diagnostics = _discover_probe_sources(path)
    if discovery_diagnostics:
        return {}, discovery_diagnostics
    if not sources:
        return {}, [Diagnostic(str(path), "structure", "no *.probe.yaml files found")]
    try:
        for source in sources:
            errors = _probe_file_preflight(source)
            if errors:
                return {}, errors

        diagnostics: list[Diagnostic] = []
        probes: dict[str, dict[str, Any]] = {}
        schema = json.loads(SCHEMA.read_text())
        validator = Draft202012Validator(schema)
        obligations = {
            item.id: item
            for item in list(enumerate_obligations(definition))
            + list(enumerate_architecture_obligations(definition))
        }
        actors = set(definition.get("actors", {}))
        for source in sources:
            encoded, errors = _read_probe_source(source)
            if errors:
                # An oversized or otherwise unsafe accepted file invalidates the
                # whole discovery result; no previously loaded subset is usable.
                return {}, errors
            assert encoded is not None
            probe, errors = _load_probe_encoded(source.path, encoded)
            diagnostics.extend(errors)
            if probe is None:
                continue
            schema_errors = list(validator.iter_errors(probe))
            for error in sorted(schema_errors, key=lambda item: list(item.absolute_path)):
                diagnostics.append(
                    Diagnostic(f"{source.path}:{_path(error.absolute_path)}", "schema", error.message)
                )
            if schema_errors:
                continue

            probe_id = probe["probe"]
            if probe_id in probes:
                diagnostics.append(
                    Diagnostic(f"{source.path}:probe", "duplicate-probe", f"probe '{probe_id}' is already defined")
                )
            else:
                probes[probe_id] = probe

            obligation = obligations.get(probe["verifies"])
            if obligation is None:
                diagnostics.append(
                    Diagnostic(f"{source.path}:verifies", "undefined-reference", f"unknown obligation '{probe['verifies']}'")
                )
            elif bindings is not None:
                configured = verification_plan(bindings, obligation).get("probes", {})
                if probe_id not in configured:
                    diagnostics.append(
                        Diagnostic(f"{source.path}:probe", "unbound-probe", "probe has no approved coverage binding")
                    )

            captured: set[str] = set()
            for section in ("setup", "steps"):
                for index, step in enumerate(probe.get(section, [])):
                    serialized = json.dumps(step)
                    for variable in VARIABLE.findall(serialized):
                        if variable not in captured:
                            diagnostics.append(
                                Diagnostic(f"{source.path}:{section}[{index}]", "undefined-variable", f"variable '{variable}' is used before capture")
                            )
                    actor = step.get("as")
                    if actor is not None and actor not in actors:
                        diagnostics.append(
                            Diagnostic(f"{source.path}:{section}[{index}].as", "undefined-reference", f"unknown actor '{actor}'")
                        )
                    for variable in step.get("capture", {}):
                        if variable in captured:
                            diagnostics.append(
                                Diagnostic(f"{source.path}:{section}[{index}].capture.{variable}", "duplicate-capture", f"variable '{variable}' is already captured")
                        )
                        captured.add(variable)
        return probes, diagnostics
    finally:
        _close_probe_sources(sources)


def missing_probe_diagnostics(
    probes: dict[str, dict[str, Any]], definition: dict[str, Any], bindings: dict[str, Any]
) -> list[Diagnostic]:
    """Report probe IDs required by product bindings but absent from the source set."""

    available = set(probes)
    diagnostics: list[Diagnostic] = []
    for obligation in list(enumerate_obligations(definition)) + list(enumerate_architecture_obligations(definition)):
        for probe_id in verification_plan(bindings, obligation).get("probes", {}):
            if probe_id not in available:
                diagnostics.append(
                    Diagnostic(obligation.id, "missing-probe", f"approved probe '{probe_id}' has no definition")
                )
    return diagnostics
