"""Library-loan design evaluation fixture."""

from __future__ import annotations

from loans.domain.policy import Policy


class Quoting:
    def __init__(self, policy: Policy) -> None:
        self._policy = policy

    def quote(self, days: int) -> int:
        return self._policy.fee(days)
