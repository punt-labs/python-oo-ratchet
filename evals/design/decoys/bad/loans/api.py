"""Library-loan design evaluation fixture."""

from __future__ import annotations

from .adapters.wire import Codec
from .domain.policy import Policy, StandardPolicy


def quote(days: int) -> int:
    if days < 0:
        raise ValueError("days must be nonnegative")
    loan = Codec.from_wire({"days": days, "rate": 2})
    policy: Policy = StandardPolicy()
    return policy.fee(loan.days)
