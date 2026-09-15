"""Shared validation diagnostic type."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


DiagnosticSeverity = Literal["error", "warning"]


@dataclass(frozen=True)
class Diagnostic:
    path: str
    code: str
    message: str
    severity: DiagnosticSeverity = "error"

    def __post_init__(self) -> None:
        if self.severity not in {"error", "warning"}:
            raise ValueError(f"unsupported diagnostic severity: {self.severity}")

    def format(self) -> str:
        return f"{self.path}: [{self.severity}] [{self.code}] {self.message}"
