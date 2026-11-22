"""Library-loan design evaluation fixture."""

from __future__ import annotations

from typing import Protocol


class Policy(Protocol):
    def fee(self, days: int) -> int: ...


class Book:
    def fee(self, days: int) -> int:
        return days * 2


class Dvd:
    def fee(self, days: int) -> int:
        return days * 3


class Ebook:
    def fee(self, days: int) -> int:
        return days


def policies() -> tuple[Policy, ...]:
    return Book(), Dvd(), Ebook()
