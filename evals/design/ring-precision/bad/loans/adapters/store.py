"""Library-loan design evaluation fixture."""

from __future__ import annotations


class FeeStore:
    def __init__(self) -> None:
        self._rate = 2

    def rate(self) -> int:
        return self._rate
