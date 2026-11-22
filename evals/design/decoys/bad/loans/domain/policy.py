"""Library-loan design evaluation fixture."""

from __future__ import annotations

from typing import Protocol


class Policy(Protocol):
    def fee(self, days: int) -> int: ...


class StandardPolicy:
    def fee(self, days: int) -> int:
        return days * 2
