"""Library-loan design evaluation fixture."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Loan:
    days: int
    rate: int
    grace: int
    limit: int
