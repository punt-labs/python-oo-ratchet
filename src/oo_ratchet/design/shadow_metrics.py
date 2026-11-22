"""Reuse the OO gate's per-file comparisons, without baselines or waivers."""

from __future__ import annotations

from dataclasses import asdict
from typing import Self

from oo_ratchet.oo.compare import FileReview, Review, Row


class ShadowMetrics:
    """Compare measured base values, keeping every metric separate."""

    _review: Review

    def __new__(
        cls, base: dict[str, dict[str, float]], current: dict[str, dict[str, float]]
    ) -> Self:
        self = super().__new__(cls)
        self._review = Review(
            tuple(
                FileReview(path, current[path], base.get(path), None, frozenset())
                for path in sorted(current)
            )
        )
        return self

    @property
    def rows(self) -> tuple[Row, ...]:
        """Return the OO gate's deltas, including absolute checks for new files."""
        return self._review.rows

    @property
    def improved(self) -> tuple[tuple[str, str], ...]:
        """Return the (file, metric) pairs that strictly improved."""
        rows = self._review.rows
        return tuple((r.file, r.metric) for r in rows if r.status == "IMPROVED")

    @property
    def regressed(self) -> tuple[tuple[str, str], ...]:
        """Return the OO gate's unwaived regression list."""
        return self._review.regressions

    def mapping(self, *, trade: bool) -> dict[str, object]:
        """Return deltas and make accepted trade regressions explicit."""
        return {
            "deltas": [asdict(row) for row in self.rows],
            "improved": self.improved,
            "regressed": self.regressed,
            "accepted": self.regressed if trade else (),
        }
