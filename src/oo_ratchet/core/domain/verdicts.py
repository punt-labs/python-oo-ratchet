"""Reviews, verdicts and waivers: the outcome of judging a change."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple, Self


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

    def render(self) -> str:
        """Return the row formatted for the comparison table."""
        return (
            f"{self.path:<40} {self.metric:<26} {self.baseline:>10} "
            f"{self.current:>10} {self.delta:>8} {self.status:>10}"
        )

    def as_delta(self) -> dict[str, str]:
        """Return the row as the mapping a JSON delta list holds."""
        return {
            "file": self.path,
            "metric": self.metric,
            "baseline": self.baseline,
            "current": self.current,
            "delta": self.delta,
            "status": self.status,
        }


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

    @property
    def tracked(self) -> bool:
        """Return whether the file has a base row."""
        return self.base_present

    @property
    def has_waiver(self) -> bool:
        """Return whether a regression on this file was waived."""
        return bool(self.waived)

    def regressions(self) -> tuple[tuple[str, str], ...]:
        """Return this file's unwaived ``(path, metric)`` regressions."""
        return tuple((self.path, m) for m in self.regressed)

    def credits(self, *, tracked_present: bool) -> bool:
        """Return whether this file earns the must-improve credit.

        When any touched file is tracked, only an improvement on a tracked file
        counts; otherwise a new file that clears every target does.
        """
        return self.improved if tracked_present else self.new_passes


@dataclass(frozen=True, slots=True)
class Review:
    """The per-file reviews of one change and the whole-change gates on them."""

    files: tuple[FileReview, ...]

    @property
    def rows(self) -> tuple[MetricRow, ...]:
        """Return every reportable row across all reviewed files."""
        return tuple(row for review in self.files for row in review.rows)

    @property
    def regressions(self) -> tuple[tuple[str, str], ...]:
        """Return the unwaived (path, metric) regressions."""
        return tuple(pair for r in self.files for pair in r.regressions())

    @property
    def has_regression(self) -> bool:
        """Return whether any unwaived regression exists."""
        return bool(self.regressions)

    @property
    def has_waiver(self) -> bool:
        """Return whether any regression was waived."""
        return any(r.has_waiver for r in self.files)

    @property
    def improvement_satisfied(self) -> bool:
        """Return whether the must-improve gate is met.

        A waiver exempts the change. Otherwise, when any touched file is in the
        base, the improvement must come from such a file; a pure-add change is
        satisfied by new files that clear every target.
        """
        if self.has_waiver:
            return True
        present = any(r.tracked for r in self.files)
        return any(r.credits(tracked_present=present) for r in self.files)


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
