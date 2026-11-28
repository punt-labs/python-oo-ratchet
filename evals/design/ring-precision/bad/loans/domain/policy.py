"""Library-loan design evaluation fixture."""

from __future__ import annotations

from loans.adapters.store import FeeStore


class Policy:
    def __init__(self) -> None:
        self._store = FeeStore()

    def fee(self, days: int) -> int:
        if days < 0:
            raise ValueError("days must be nonnegative")
        return days * self._store.rate()
