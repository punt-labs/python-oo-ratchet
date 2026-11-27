"""Compare measured base values with the OO gate's policy, without baselines."""

from __future__ import annotations

from typing import ClassVar, Self

from oo_ratchet.core.application.policy import GatePolicy
from oo_ratchet.core.domain.verdicts import MetricRow, Review
from oo_ratchet.oo.thresholds import Thresholds


class ShadowMetrics:
    """Compare measured base values with the OO gate's policy, metric by metric.

    Baselines and waivers play no part: every file is judged against the
    values measured at the merge base.
    """

    POLICY: ClassVar[GatePolicy] = GatePolicy.from_table(
        Thresholds.TABLE, Thresholds.CEILINGS
    )

    _review: Review

    def __new__(
        cls, base: dict[str, dict[str, float]], current: dict[str, dict[str, float]]
    ) -> Self:
        self = super().__new__(cls)
        self._review = Review(
            tuple(
                cls.POLICY.review(
                    path, current[path], base.get(path), None, frozenset()
                )
                for path in sorted(current)
            )
        )
        return self

    @property
    def rows(self) -> tuple[MetricRow, ...]:
        """Return the OO gate's deltas, including absolute checks for new files."""
        return self._review.rows

    @property
    def improved(self) -> tuple[tuple[str, str], ...]:
        """Return the (file, metric) pairs that strictly improved."""
        return tuple((r.path, r.metric) for r in self.rows if r.status == "IMPROVED")

    @property
    def regressed(self) -> tuple[tuple[str, str], ...]:
        """Return the unwaived regression list."""
        return self._review.regressions

    def mapping(self, *, trade: bool) -> dict[str, object]:
        """Return deltas and make accepted trade regressions explicit."""
        return {
            "deltas": [self._delta(row) for row in self.rows],
            "improved": self.improved,
            "regressed": self.regressed,
            "accepted": self.regressed if trade else (),
        }

    @staticmethod
    def _delta(row: MetricRow) -> dict[str, str]:
        return {
            "file": row.path,
            "metric": row.metric,
            "baseline": row.baseline,
            "current": row.current,
            "delta": row.delta,
            "status": row.status,
        }
