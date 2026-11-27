"""The total-count gate's command surface: verdict reports and write guard."""

from __future__ import annotations

from typing import ClassVar, Self

from oo_ratchet.core.domain.tallies import TallyRecord
from oo_ratchet.core.domain.totals import TotalReview
from oo_ratchet.core.domain.verdicts import Failure, Verdict


class TallyCli:
    """Render a ``Verdict`` of a total-count gate as report lines.

    ``ledger`` names the ceiling ledger a waived total points to.
    """

    MESSAGES: ClassVar[dict[str, str]] = {
        "base-unresolvable": "base ref unresolvable and --require-base is set",
        "base-stale": (
            "cannot resolve merge-base (origin/main unfetched or stale) with an "
            "in-tree baseline present; fetch origin/main or pass --base-ref"
        ),
        "tripwire-no-baseline": (
            "--tripwire with no baseline on main; only the adoption commit "
            "that adds the baseline may bootstrap"
        ),
        "tip-unresolvable": (
            "base has no scanned source tree and origin/main is unresolvable "
            "with an in-tree baseline present; fetch origin/main"
        ),
        "base-predates-baseline": (
            "base commit predates the scanned source tree; rebase onto current main"
        ),
        "ci-write": (
            "refusing to write suppression baseline under GITHUB_ACTIONS "
            "without --allow-ci-write"
        ),
        "blank-justification": "--relax requires a non-empty --justify",
        "blank-reason": "--rebaseline requires --reason <text>",
        "relax-no-base": (
            "cannot resolve comparison base for --relax (base_ref={0}); "
            "nothing was relaxed"
        ),
        "relax-absent-base": "{0} does not exist at base {1}; nothing was relaxed",
        "nothing-to-relax": "nothing to relax for {0} (no rise)",
    }
    BOOTSTRAPS: ClassVar[dict[str, str]] = {
        "first-adoption: no base and no in-tree baseline": (
            "No base and no in-tree baseline -- first-adoption bootstrap pass"
        ),
        "tripwire: base predates baseline adoption": (
            "Base predates baseline adoption on push tripwire -- "
            "one-time bootstrap pass"
        ),
        "first-adoption: no base baseline and no tip": (
            "No source tree at base and no origin/main -- first-adoption bootstrap pass"
        ),
        "first-adoption: no baseline at base or tip": (
            "No source tree at base or origin/main tip -- first-adoption bootstrap pass"
        ),
    }

    _ledger: str

    def __new__(cls, ledger: str) -> Self:
        self = super().__new__(cls)
        self._ledger = ledger
        return self

    @staticmethod
    def exit_code(verdict: Verdict) -> int:
        """Return 0 for a passing verdict, 1 for a failing one."""
        return 0 if verdict.passed else 1

    def text(self, verdict: Verdict) -> list[str]:
        """Return the report lines."""
        if verdict.totals is not None:
            return self._totals(verdict.totals, verdict.failures)
        if verdict.record is not None:
            return self._written(verdict.record, verdict.written[0])
        if verdict.failures:
            return [self._failure(f) for f in verdict.failures]
        return [self.BOOTSTRAPS.get(verdict.note, verdict.note)]

    def _failure(self, failure: Failure) -> str:
        what = self.MESSAGES.get(failure.kind, failure.kind)
        return "FAIL: " + what.format(*failure.subjects)

    def _totals(self, review: TotalReview, failures: tuple[Failure, ...]) -> list[str]:
        base, raw = review.baseline_total, review.raw_total
        if any(f.kind == "raise-refused" for f in failures):
            rise = raw - base
            return [
                f"\nBaseline total: {base}",
                f"Current total:  {raw}",
                (
                    f"\nFAIL: refusing to raise the suppression baseline by {rise} "
                    f"({base} -> {raw}); update never loosens"
                ),
            ]
        waived = (
            f" ({review.waived} waived, see {self._ledger})" if review.waived else ""
        )
        head = [f"\nBaseline total: {base}", f"Current total:  {raw}{waived}"]
        if review.increased:
            return head + self._regression(review)
        drop = base - review.effective_total
        if drop > 0:
            return [*head, f"\nPASS: suppression count decreased by {drop}"]
        return [*head, "\nPASS: suppression count unchanged"]

    @staticmethod
    def _regression(review: TotalReview) -> list[str]:
        diff = review.effective_total - review.baseline_total
        return [
            f"\nFAIL: suppression count increased by {diff} (after waivers)",
            "\nFiles with new or increased, unwaived suppressions:",
            *(
                f"  {r.path}: +{r.unwaived} unwaived ({r.base} -> {r.current})"
                for r in review.rises
            ),
        ]

    @staticmethod
    def _written(record: TallyRecord, path: str) -> list[str]:
        if record.kind == "update":
            return [
                f"\nBaseline updated: {path}",
                f"  total: {record.total}",
                *(f"  {c}: {n}" for c, n in sorted(record.by_category.items())),
            ]
        if record.kind == "relaxed":
            return [
                (
                    f"\nRelaxed {record.file}: ceiling set to {record.after} "
                    f"(was {record.before}, reason: {record.reason})"
                ),
                f"  ledger: {path}",
            ]
        before = "(none)" if record.before is None else record.before
        return [
            f"\nBaseline rebaselined: {path} (reason: {record.reason})",
            f"  total: {before} -> {record.total}",
        ]
