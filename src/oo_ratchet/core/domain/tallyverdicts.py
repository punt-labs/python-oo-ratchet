"""The result of an operation of a gate that compares a total count."""

from __future__ import annotations

from dataclasses import dataclass

from .tallies import TallyRecord
from .totals import TotalReview
from .verdicts import Failure, Verdict


@dataclass(frozen=True, slots=True)
class TallyVerdict:
    """A verdict, with the total comparison or the audited write behind it.

    ``totals`` is set when two totals were compared (a check, or an update
    refused for raising the total); ``record`` when a write succeeded.
    """

    verdict: Verdict
    totals: TotalReview | None = None
    record: TallyRecord | None = None

    @property
    def passed(self) -> bool:
        """Return whether the operation succeeded."""
        return self.verdict.passed

    @property
    def failures(self) -> tuple[Failure, ...]:
        """Return the reasons the operation failed."""
        return self.verdict.failures
