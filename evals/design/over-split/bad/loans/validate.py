"""One prematurely extracted loan operation."""

from __future__ import annotations


class Validate:
    def validate(self, value: int) -> int:
        if value < 0:
            raise ValueError("days must be nonnegative")
        return value
