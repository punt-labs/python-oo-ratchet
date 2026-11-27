"""Reviews, verdicts and waivers: the outcome of judging a change."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple, Self

from .tallies import TallyRecord
from .totals import TotalReview


class Waiver(NamedTuple):
    """An audited permission for one file's metric to be worse than its base."""

    path: str
    metric: str


@dataclass(frozen=True, slots=True)
class MetricRow:
    """One metric comparison line of a check report."""

    path: str
    metric: str
    baseline: str
    current: str
    delta: str
    status: str


@dataclass(frozen=True, slots=True)
class FileReview:
    """One touched file judged against its base row."""

    path: str
    rows: tuple[MetricRow, ...] = ()
    regressed: tuple[str, ...] = ()
    waived: tuple[str, ...] = ()
    improved: bool = False
    base_present: bool = False
    new_passes: bool = False


@dataclass(frozen=True, slots=True)
class Review:
    """The per-file reviews of one change and the whole-change gates on them."""

    files: tuple[FileReview, ...]

    @property
    def regressions(self) -> tuple[tuple[str, str], ...]:
        """Return the unwaived (path, metric) regressions."""
        return tuple((r.path, m) for r in self.files for m in r.regressed)

    @property
    def has_regression(self) -> bool:
        """Return whether any unwaived regression exists."""
        return bool(self.regressions)

    @property
    def has_waiver(self) -> bool:
        """Return whether any regression was waived."""
        return any(r.waived for r in self.files)

    @property
    def improvement_satisfied(self) -> bool:
        """Return whether the must-improve gate is met.

        A waiver exempts the change. Otherwise, when any touched file is in the
        base, the improvement must come from such a file; a pure-add change is
        satisfied by new files that clear every target.
        """
        if self.has_waiver:
            return True
        existing = [r for r in self.files if r.base_present]
        if existing:
            return any(r.improved for r in existing)
        return any(r.new_passes for r in self.files)


@dataclass(frozen=True, slots=True)
class Failure:
    """One reason a verdict failed, naming what it concerns."""

    kind: str
    subjects: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Verdict:
    """The result of an operation: failures (none means pass) and a note."""

    failures: tuple[Failure, ...] = ()
    note: str = ""
    review: Review | None = None
    improved: int = 0
    removed: tuple[str, ...] = ()
    written: tuple[str, ...] = ()
    totals: TotalReview | None = None
    record: TallyRecord | None = None

    @property
    def passed(self) -> bool:
        """Return whether the operation succeeded."""
        return not self.failures

    @classmethod
    def ok(cls, note: str = "", *, written: tuple[str, ...] = ()) -> Self:
        """Return a passing verdict carrying ``note`` and the rows written."""
        return cls(note=note, written=written)

    @classmethod
    def refused(cls, kind: str, *subjects: str) -> Self:
        """Return a failing verdict with one failure."""
        return cls(failures=(Failure(kind, subjects),))
