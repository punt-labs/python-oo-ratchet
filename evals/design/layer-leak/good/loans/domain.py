"""Library-loan design evaluation fixture."""

from __future__ import annotations

from typing import Protocol


class Rates(Protocol):
    def rate(self) -> int: ...


def fee(days: int, rates: Rates) -> int:
    if days < 0:
        raise ValueError("days must be nonnegative")
    return days * rates.rate()
