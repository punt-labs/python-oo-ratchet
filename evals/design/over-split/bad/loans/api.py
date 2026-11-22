"""Library-loan design evaluation fixture."""

from __future__ import annotations

from .cap import Cap
from .grace import Grace
from .multiply import Multiply
from .receipt import Receipt
from .round import Round
from .validate import Validate


def quote(days: int) -> int:
    """Quote the late fee in cents."""
    if days < 0:
        raise ValueError("days must be nonnegative")
    return Receipt().receipt(
        Round().round_fee(
            Cap().cap(Multiply().multiply(Grace().deduct(Validate().validate(days))))
        )
    )
