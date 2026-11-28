"""Library-loan design evaluation fixture."""

from __future__ import annotations


class Policy:
    def __init__(self, rate: int) -> None:
        self._rate = rate

    def fee(self, days: int) -> int:
        if days < 0:
            raise ValueError("days must be nonnegative")
        return days * self._rate
