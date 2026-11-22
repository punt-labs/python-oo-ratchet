"""One prematurely extracted loan operation."""

from __future__ import annotations

from .rules import FeeRules


class Multiply:
    def multiply(self, value: int) -> int:
        return value * FeeRules.daily_rate()
