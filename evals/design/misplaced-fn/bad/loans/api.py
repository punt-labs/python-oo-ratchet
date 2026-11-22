"""Library-loan design evaluation fixture."""

from __future__ import annotations

from .loan import Loan, fee


def quote(days: int) -> int:
    """Quote the late fee in cents."""
    if days < 0:
        raise ValueError("days must be nonnegative")
    return fee(Loan(days, 2))
