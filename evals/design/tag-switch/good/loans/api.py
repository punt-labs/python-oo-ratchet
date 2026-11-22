"""Library-loan design evaluation fixture."""

from __future__ import annotations

from .policy import policies


def quote(days: int) -> int:
    """Quote the late fee in cents."""
    if days < 0:
        raise ValueError("days must be nonnegative")
    return sum(policy.fee(days) for policy in policies()) // 3
