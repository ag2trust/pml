"""Shared strict format checks for PML schemas."""

from __future__ import annotations

from datetime import datetime

from jsonschema import FormatChecker


FORMAT_CHECKER = FormatChecker()


@FORMAT_CHECKER.checks("date-time", raises=(TypeError, ValueError))
def valid_date_time(value: object) -> bool:
    """Validate calendar and clock fields even without optional jsonschema extras."""

    if not isinstance(value, str):
        return True
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.tzinfo is not None
