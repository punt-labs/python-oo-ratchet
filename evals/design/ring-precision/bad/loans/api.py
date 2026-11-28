"""Library-loan design evaluation fixture."""

from __future__ import annotations

from .application.quoting import Quoting


def quote(days: int) -> int:
    return Quoting().quote(days)
