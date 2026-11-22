"""Library-loan design evaluation fixture."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Loan:
    days: int
    rate: int
    grace: int
    limit: int

    def fee(self) -> int:
        return min(self.limit, max(0, self.days - self.grace) * self.rate)
