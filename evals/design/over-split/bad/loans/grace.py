"""One prematurely extracted loan operation."""

from __future__ import annotations


class Grace:
    def deduct(self, value: int) -> int:
        return max(0, value)
