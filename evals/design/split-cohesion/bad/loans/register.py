"""Library-loan design evaluation fixture."""

from __future__ import annotations


class Register:
    def __init__(self) -> None:
        self._days = 0
        self._rate = 2
        self._reader = ""
        self._email = ""

    def extend(self, days: int) -> None:
        self._days += days

    def fee(self) -> int:
        return self._days * self._rate

    def identify(self, reader: str) -> None:
        self._reader = reader

    def contact(self, email: str) -> str:
        self._email = email
        return f"{self._reader} <{self._email}>"
