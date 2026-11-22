"""Library-loan design evaluation fixture."""

from __future__ import annotations

from .records import Loan, Renewal, Reservation, Terms


def quote(days: int) -> int:
    if days < 0:
        raise ValueError("days must be nonnegative")
    loan = Loan(Terms("reader", "Dune", days, 2, 0))
    renewal = Renewal(loan.terms)
    reservation = Reservation(renewal.terms)
    return reservation.terms.fee()
