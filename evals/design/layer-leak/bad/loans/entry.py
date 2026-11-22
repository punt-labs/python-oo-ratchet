"""Library-loan design evaluation fixture."""

from __future__ import annotations

from .domain import rate


def quote(days: int) -> int:
    if days < 0:
        raise ValueError("days must be nonnegative")
    if days == 0:
        return 0
    if days < 7:
        return days * rate()
    if days < 14:
        return (days // 7 * 7 + days % 7) * rate()
    if days < 21:
        return sum(rate() for _ in range(days))
    return days * rate()
