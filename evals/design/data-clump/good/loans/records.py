"""Library-loan design evaluation fixture."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Terms:
    borrower: str
    title: str
    days: int
    rate: int
    grace: int

    def fee(self) -> int:
        return max(0, self.days - self.grace) * self.rate


@dataclass(frozen=True)
class Loan:
    terms: Terms


@dataclass(frozen=True)
class Renewal:
    terms: Terms


@dataclass(frozen=True)
class Reservation:
    terms: Terms
