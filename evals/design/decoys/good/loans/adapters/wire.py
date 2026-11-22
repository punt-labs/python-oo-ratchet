"""Library-loan design evaluation fixture."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LoanWire:
    days: int
    rate: int
    borrower: str


class Codec:
    @classmethod
    def from_wire(cls, raw: dict[str, int]) -> LoanWire:
        return LoanWire(raw["days"], raw["rate"], "reader")
