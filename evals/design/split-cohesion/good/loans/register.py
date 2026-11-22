"""Library-loan design evaluation fixture."""

from __future__ import annotations


class Loan:
    def __init__(self) -> None:
        self._days = 0
        self._rate = 2

    def extend(self, days: int) -> None:
        self._days += days

    def fee(self) -> int:
        return self._days * self._rate


class Reader:
    def __init__(self) -> None:
        self._name = ""
        self._email = ""

    def identify(self, reader: str) -> None:
        self._name = reader

    def contact(self, email: str) -> str:
        self._email = email
        return f"{self._name} <{self._email}>"
