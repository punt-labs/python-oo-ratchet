"""Library-loan design evaluation fixture."""

from __future__ import annotations

from .register import Loan, Reader


def quote(days: int) -> int:
    if days < 0:
        raise ValueError("days must be nonnegative")
    reader = Reader()
    reader.identify("reader")
    reader.contact("reader@example.org")
    loan = Loan()
    loan.extend(days)
    return loan.fee()
