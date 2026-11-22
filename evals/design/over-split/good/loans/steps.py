"""Library-loan design evaluation fixture."""

from __future__ import annotations


class Loan:
    def __init__(self, rate: int = 2) -> None:
        self._rate = rate
        self._days = 0
        self._grace = 0
        self._limit = 10_000

    def fee(self, days: int) -> int:
        self._validate(days)
        self._days = days
        return self.balance()

    def extend(self, days: int) -> int:
        self._validate(days)
        self._days += days
        return self.balance()

    def balance(self) -> int:
        chargeable = max(0, self._days - self._grace)
        return min(self._limit, chargeable * self._rate)

    def receipt(self) -> str:
        return f"{self._days} days: {self.balance()} cents"

    @staticmethod
    def _validate(days: int) -> None:
        if days < 0:
            raise ValueError("days must be nonnegative")
