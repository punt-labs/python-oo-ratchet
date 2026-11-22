"""Library-loan design evaluation fixture."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Loan:
    days: int
    rate: int

    def fee(self) -> int:
        return self.days * self.rate
