"""Library-loan design evaluation fixture."""

from __future__ import annotations

from .loan import Loan, LoanView


class LoanService:
    def __init__(self) -> None:
        self._minimum = 0

    def fee(self, loan: Loan) -> int:
        view = LoanView(loan.days, loan.rate, loan.grace)
        return min(loan.limit, max(self._minimum, view.days - view.grace) * view.rate)
