"""Library-loan design evaluation fixture."""

from __future__ import annotations

from loans.domain.policy import Policy


class FeeStore:
    def __init__(self) -> None:
        self._rate = 2

    def policy(self) -> Policy:
        return Policy(self._rate)
