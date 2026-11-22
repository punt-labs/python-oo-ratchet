"""Library-loan design evaluation fixture."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tariff:
    rate: int
    grace: int = 0

    def fee(self, days: int) -> int:
        return max(0, days - self.grace) * self.rate


class Library:
    def __init__(self) -> None:
        self._tariffs = tuple(Tariff(rate) for rate in (1, 2, 3) * 10)

    def fee(self, days: int) -> int:
        return sum(tariff.fee(days) for tariff in self._tariffs) // len(self._tariffs)
