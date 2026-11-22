"""Library-loan design evaluation fixture."""

from __future__ import annotations

from .domain import Rates, fee


def quote(days: int, rates: Rates) -> int:
    return fee(days, rates)
