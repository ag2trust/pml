"""Canonical byte encodings for approved PML derived artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from pml.compiled_model import CompiledModel


def _encoded_string(value: str) -> str:
    """Encode one scalar string with the spelling fixed by spec 0011."""

    return json.dumps(value, ensure_ascii=False)


def _sorted_items(value: Mapping[Any, Any]) -> list[tuple[str, Any]]:
    if not all(isinstance(key, str) for key in value):
        raise TypeError("canonical JSON object keys must be strings")
    return sorted(value.items())


def _is_array(value: object) -> bool:
    return isinstance(value, list)


def _compact(value: Any) -> str:
    if isinstance(value, str):
        return _encoded_string(value)
    if isinstance(value, Mapping):
        return "{" + ",".join(
            f"{_encoded_string(key)}:{_compact(child)}"
            for key, child in _sorted_items(value)
        ) + "}"
    if _is_array(value):
        return "[" + ",".join(_compact(child) for child in value) + "]"
    raise TypeError("canonical definition JSON contains only objects, arrays, and strings")


def _pretty(value: Any, depth: int = 0) -> str:
    if isinstance(value, str):
        return _encoded_string(value)
    if type(value) is int and value == 1:
        return "1"
    if isinstance(value, Mapping):
        items = _sorted_items(value)
        if not items:
            return "{}"
        child_indent = "  " * (depth + 1)
        body = ",\n".join(
            f"{child_indent}{_encoded_string(key)}: {_pretty(child, depth + 1)}"
            for key, child in items
        )
        return f"{{\n{body}\n{'  ' * depth}}}"
    if _is_array(value):
        if not value:
            return "[]"
        child_indent = "  " * (depth + 1)
        body = ",\n".join(
            f"{child_indent}{_pretty(child, depth + 1)}" for child in value
        )
        return f"[\n{body}\n{'  ' * depth}]"
    raise TypeError(
        "compiled-model JSON contains only objects, arrays, strings, and format version 1"
    )


def canonical_definition_bytes(document: Mapping[str, Any]) -> bytes:
    """Encode a valid merged definition for its approved SHA-256 digest."""

    return _compact(document).encode("utf-8")


def definition_digest(document: Mapping[str, Any]) -> str:
    """Return the definition digest fixed by the compiled-model v1 contract."""

    encoded = canonical_definition_bytes(document)
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _canonical_compiled_json_bytes(value: Any) -> bytes:
    """Encode a value with the compiled-model v1 layout (for conformance tests)."""

    return (_pretty(value) + "\n").encode("utf-8")


def serialize_compiled_model(model: CompiledModel) -> bytes:
    """Serialize a compiled-model v1 value to its canonical, newline-ended bytes."""

    return _canonical_compiled_json_bytes(model)
