"""Library-loan design evaluation fixture."""

from __future__ import annotations

from .loan import Loan


class LoanService:
    def __init__(self) -> None:
        self._minimum = 0

    def fee(self, loan: Loan) -> int:
        return min(loan.limit, max(self._minimum, loan.days - loan.grace) * loan.rate)
