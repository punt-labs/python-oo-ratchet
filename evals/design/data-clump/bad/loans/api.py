"""Library-loan design evaluation fixture."""

from __future__ import annotations

from .records import Loan, Renewal, Reservation


def quote(days: int) -> int:
    if days < 0:
        raise ValueError("days must be nonnegative")
    loan = Loan("reader", "Dune", days, 2, 0)
    renewal = Renewal(loan.borrower, loan.title, loan.days, loan.rate, loan.grace)
    reservation = Reservation(
        renewal.borrower, renewal.title, renewal.days, renewal.rate, renewal.grace
    )
    return max(0, reservation.days - reservation.grace) * reservation.rate
