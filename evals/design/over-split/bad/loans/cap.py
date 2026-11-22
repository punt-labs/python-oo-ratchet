"""One prematurely extracted loan operation."""

from __future__ import annotations

from .rules import FeeRules


class Cap:
    def cap(self, value: int) -> int:
        return min(FeeRules.maximum_fee(), value)
