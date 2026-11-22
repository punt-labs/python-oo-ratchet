"""Library-loan design evaluation fixture."""

from __future__ import annotations

from .loan import Loan


def quote(days: int) -> int:
    """Quote the late fee in cents."""
    if days < 0:
        raise ValueError("days must be nonnegative")
    return Loan(days, 2, 0, 10_000).fee()
