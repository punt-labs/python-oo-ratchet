"""Library-loan design evaluation fixture."""

from __future__ import annotations


def due(days: int, tz: str, grace: int) -> int:
    if tz != "UTC":
        raise ValueError("unsupported timezone")
    return max(0, days - grace) * 2
