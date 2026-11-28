"""The shared gate command surface: verdict reports, text and ``--json``."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import ClassVar, Self

from oo_ratchet.core.adapters.outcomelog import OutcomeLog
from oo_ratchet.core.domain.verdicts import Failure, MetricRow, Verdict


class GateCli:
    """Render a ``Verdict`` for a gate and guard its writes.

    ``fix`` is the command a person runs to refresh the baseline.
    """

    MESSAGES: ClassVar[dict[str, str]] = {
        "base-unresolvable": "base ref unresolvable and --require-base is set",
        "base-stale": (
            "cannot resolve merge-base (origin/main unfetched or stale) with an "
            "in-tree baseline present; fetch origin/main or pass --base-ref"
        ),
        "base-empty": "base baseline is empty (truncated write or bad merge)",
        "tripwire-no-baseline": "--tripwire with no baseline on main",
        "tip-unresolvable": "base has no baseline and origin/main is unresolvable",
        "base-predates-baseline": "base commit predates baseline adoption; rebase",
        "parse-error": "touched file(s) failed to parse",
        "parse-refused": "REFUSED, unparseable, baseline kept",
        "missing-row": "touched file(s) not in baseline",
        "stale-row": "baseline out of date",
        "regression": "regression detected",
        "ci-write": (
            "refusing to write baseline under GITHUB_ACTIONS without --allow-ci-write"
        ),
        "no-improvement": "no metric improved on any touched file",
        "refused": "REFUSED, nothing written for these",
        "blank-justification": "--relax requires a non-empty --justify",
        "blank-reason": "a non-blank --reason is required",
        "not-scored": "not a scored file",
        "no-row": "no baseline entry to relax",
        "nothing-to-relax": "nothing to relax: no metric is worse than its baseline",
    }
    HEADER: ClassVar[str] = (
        f"\n{'File':<40} {'Metric':<26} {'Baseline':>10} "
        f"{'Current':>10} {'Delta':>8} {'Status':>10}"
    )

    _fix: str

    def __new__(cls, fix: str) -> Self:
        self = super().__new__(cls)
        self._fix = fix
        return self

    @staticmethod
    def exit_code(verdict: Verdict) -> int:
        """Return 0 for a passing verdict, 1 for a failing one; log a refusal."""
        OutcomeLog(verdict.failures).refused()
        return 0 if verdict.passed else 1

    def text(self, verdict: Verdict) -> list[str]:
        """Return the report lines."""
        lines: list[str] = []
        if verdict.review is not None:
            rows = [r for f in verdict.review.files for r in f.rows]
            lines += [self.HEADER, "-" * 108, *map(self._row, rows)]
            if not rows:
                lines.append("  (all metrics unchanged)")
        lines += [self._failure(f) for f in verdict.failures]
        lines += [f"  written: {path}" for path in verdict.written]
        if verdict.passed:
            lines.append(f"PASS: {verdict.note}" if verdict.note else "PASS")
        return lines

    @staticmethod
    def json(verdict: Verdict) -> str:
        """Return the verdict as one JSON object."""
        return json.dumps(asdict(verdict), sort_keys=True)

    @staticmethod
    def write_blocked(*, allow_ci_write: bool) -> Verdict | None:
        """Refuse a baseline write under GitHub Actions without an opt-in."""
        if os.environ.get("GITHUB_ACTIONS") == "true" and not allow_ci_write:
            return Verdict.refused("ci-write")
        return None

    def _failure(self, failure: Failure) -> str:
        what = self.MESSAGES.get(failure.kind, failure.kind)
        text = f"FAIL: {what}"
        if failure.kind in ("missing-row", "stale-row"):
            text += f" -- run {self._fix}"
        if failure.subjects:
            text += ": " + ", ".join(failure.subjects)
        return text

    @staticmethod
    def _row(row: MetricRow) -> str:
        return (
            f"{row.path:<40} {row.metric:<26} {row.baseline:>10} "
            f"{row.current:>10} {row.delta:>8} {row.status:>10}"
        )
