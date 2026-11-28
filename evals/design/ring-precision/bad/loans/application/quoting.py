"""Library-loan design evaluation fixture."""

from __future__ import annotations

from loans.domain.policy import Policy


class Quoting:
    def __init__(self) -> None:
        self._policy = Policy()

    def quote(self, days: int) -> int:
        return self._policy.fee(days)
