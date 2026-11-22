"""Library-loan design evaluation fixture."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Loan:
    days: int
    rate: int
    grace: int
    limit: int


class LoanView:
    def __init__(self, days: int, rate: int, grace: int) -> None:
        self._days = days
        self._rate = rate
        self._grace = grace

    @property
    def days(self) -> int:
        return self._days

    @property
    def rate(self) -> int:
        return self._rate

    @property
    def grace(self) -> int:
        return self._grace
