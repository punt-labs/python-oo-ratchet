"""Library-loan design evaluation fixture."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Loan:
    borrower: str
    title: str
    days: int
    rate: int
    grace: int


@dataclass(frozen=True)
class Renewal:
    borrower: str
    title: str
    days: int
    rate: int
    grace: int


@dataclass(frozen=True)
class Reservation:
    borrower: str
    title: str
    days: int
    rate: int
    grace: int
