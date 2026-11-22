"""Library-loan design evaluation fixture."""

from __future__ import annotations


def fee(kind: str, days: int) -> int:
    if kind == "book":
        return days * 2
    if kind == "dvd":
        return days * 3
    if kind == "ebook":
        return days
    raise ValueError("unknown loan kind")
