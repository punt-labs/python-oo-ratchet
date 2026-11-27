"""The total-count comparison: base against current, after ceilings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple, Self

from .ledgers import Ledger
from .tallies import Tally


class FileRise(NamedTuple):
    """A file whose count rose by more than its ceiling covers."""

    path: str
    unwaived: int
    base: int
    current: int


@dataclass(frozen=True, slots=True)
class TotalReview:
    """The base total, the current total, what ceilings waive, the rest.

    ``rises`` lists each file with an unwaived rise, sorted by path.
    """

    baseline_total: int
    raw_total: int
    waived: int = 0
    rises: tuple[FileRise, ...] = ()

    @classmethod
    def of(cls, base: Tally, current: Tally, ledger: Ledger) -> Self:
        """Compare ``current`` with ``base``; a ceiling caps a file's count.

        A ceiling never caps below the file's base count.
        """
        waived = 0
        rises: list[FileRise] = []
        for path, then, now in current.growth(base):
            rise = now - then
            ceiling = ledger.ceiling(path)
            unwaived = rise if ceiling is None else max(0, now - max(then, ceiling))
            waived += rise - unwaived
            if unwaived > 0:
                rises.append(FileRise(path, unwaived, then, now))
        return cls(base.total, current.total, waived, tuple(rises))

    @property
    def effective_total(self) -> int:
        """Return the current total less what ceilings waive."""
        return self.raw_total - self.waived

    @property
    def increased(self) -> bool:
        """Return whether the effective total is above the base total."""
        return self.effective_total > self.baseline_total
