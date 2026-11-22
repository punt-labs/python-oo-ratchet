"""One prematurely extracted loan operation."""

from __future__ import annotations


class Cap:
    def cap(self, value: int) -> int:
        return min(10_000, value)
