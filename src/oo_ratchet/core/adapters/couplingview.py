"""The coupling gate's report text: what each operation's verdict says."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Self

from oo_ratchet.core.domain.verdicts import Failure, Verdict

from .gatecli import GateCli


class CouplingView(GateCli):
    """Render a ``Verdict`` of the coupling gate as the lines it prints.

    ``baseline`` is the baseline file the write reports name.
    """

    FAILS: ClassVar[dict[str, str]] = {
        "base-unresolvable": "base ref unresolvable and --require-base is set",
        "base-stale": (
            "cannot resolve merge-base (origin/main unfetched or stale) with an "
            "in-tree baseline present; fetch origin/main or pass --base-ref"
        ),
        "base-empty": (
            "base coupling baseline is empty (truncated write or bad merge) "
            "and --require-base is set"
        ),
        "tripwire-no-baseline": (
            "--tripwire with no baseline on main; only the adoption commit "
            "that adds the baseline may bootstrap"
        ),
        "tip-unresolvable": (
            "base has no baseline and origin/main is unresolvable with an "
            "in-tree baseline present; fetch origin/main"
        ),
        "base-predates-baseline": (
            "base commit predates baseline adoption; rebase onto current main"
        ),
        "ci-write": (
            "refusing to write coupling baseline under GITHUB_ACTIONS "
            "without --allow-ci-write"
        ),
        "blank-justification": "--relax requires a non-empty --justify",
        "blank-reason": "--rebaseline-files requires --reason <text>",
        "not-scored": "not a scored file: {0}",
        "no-row": (
            "{0} has no baseline entry to relax; "
            "use --update or --rebaseline to add a new file"
        ),
        "nothing-to-relax": (
            "nothing to relax for {0} (no metric is worse than its baseline)"
        ),
        "bless-bad-ref": "cannot resolve --base-ref {0}",
        "bless-no-base-baseline": (
            "no coupling baseline at the base and --require-base is set"
        ),
    }
    UPDATE_STALE: ClassVar[str] = (
        "cannot resolve base (origin/main unfetched or stale) with a coupling "
        "baseline present; fetch origin/main, pass --base-ref, or use "
        "--rebaseline for an intentional whole-tree reset"
    )
    BOOTSTRAPS: ClassVar[dict[str, str]] = {
        "first-adoption: no base and no in-tree baseline": (
            "No base and no in-tree baseline -- first-adoption bootstrap pass"
        ),
        "tripwire: base predates baseline adoption": (
            "Base predates baseline adoption on push tripwire -- "
            "one-time bootstrap pass"
        ),
        "first-adoption: no base baseline and no tip": (
            "No base baseline and no origin/main -- first-adoption bootstrap pass"
        ),
        "first-adoption: no baseline at base or tip": (
            "No baseline at base or origin/main tip -- first-adoption bootstrap pass"
        ),
        "no scored Python files touched": "No scored Python files touched",
    }
    REPORTED: ClassVar[frozenset[str]] = frozenset(
        {"parse-refused", "regression", "refused"}
    )

    _baseline: Path

    def __new__(cls, baseline: Path) -> Self:
        self = super().__new__(cls, "")
        self._baseline = baseline
        return self

    def check(self, verdict: Verdict) -> list[str]:
        """Return the lines of a ``--check`` run."""
        review = verdict.review
        if review is None:
            return self._plain(verdict)
        rows = list(review.rows)
        lines = [self.HEADER, "-" * 108, *map(self._row, rows)]
        if not rows:
            lines.append("  (all metrics unchanged)")
        if review.has_regression:
            lines.append("\nFAIL: regression detected")
            lines += [f"  {path}: {metric}" for path, metric in review.regressions]
        else:
            lines.append("\nPASS: no regressions")
        return lines

    def update(self, verdict: Verdict) -> list[str]:
        """Return the lines of an ``--update`` run."""
        if self._early(verdict):
            return [self._fail(f, update=True) for f in verdict.failures]
        lines = [
            f"\nBaseline updated: {self._baseline}",
            f"  files improved: {verdict.improved}",
            f"  files removed:  {len(verdict.removed)}",
        ]
        for failure in verdict.failures:
            lines += self._refusal(failure)
        if verdict.passed:
            lines += [f"  backfilled: {path}" for path in verdict.written]
        return lines

    def relax(self, verdict: Verdict, file: str, justify: str) -> list[str]:
        """Return the lines of a ``--relax`` run."""
        if not verdict.passed:
            return [self._fail(f, update=False) for f in verdict.failures]
        return [
            f"\nRelaxed {file} (reason: {justify})",
            f"  baseline: {self._baseline}",
        ]

    def rebaseline(self, verdict: Verdict) -> list[str]:
        """Return the lines of a ``--rebaseline`` run."""
        if not verdict.passed:
            return [self._fail(f, update=False) for f in verdict.failures]
        return [
            f"\nBaseline reset: {self._baseline}",
            f"  files scored: {len(verdict.written)}",
        ]

    def bless(self, verdict: Verdict, reason: str) -> list[str]:
        """Return the lines of a ``--rebaseline-files`` run."""
        if self._early(verdict):
            return [self._fail(f, update=False) for f in verdict.failures]
        accepted = verdict.written
        lines = [f"\nBaseline blessed for {len(accepted)} file(s) (reason: {reason}):"]
        lines.append("  files:" if accepted else "  (none)")
        lines += [f"    {path}" for path in accepted]
        for failure in verdict.failures:
            lines.append(
                f"  REFUSED ({len(failure.subjects)} file(s), nothing written):"
            )
            lines += [f"    {why}" for why in failure.subjects]
        return lines

    def _plain(self, verdict: Verdict) -> list[str]:
        if not verdict.passed:
            return [line for f in verdict.failures for line in self._parse_or(f)]
        return [self.BOOTSTRAPS.get(verdict.note, verdict.note)]

    def _parse_or(self, failure: Failure) -> list[str]:
        if failure.kind != "parse-error":
            return [self._fail(failure, update=False)]
        return [
            "FAIL: touched file(s) failed to parse:",
            *(f"  {path}" for path in failure.subjects),
        ]

    def _early(self, verdict: Verdict) -> bool:
        return any(f.kind not in self.REPORTED for f in verdict.failures)

    def _fail(self, failure: Failure, *, update: bool) -> str:
        if update and failure.kind == "base-stale":
            return f"FAIL: {self.UPDATE_STALE}"
        what = self.FAILS.get(failure.kind, failure.kind)
        return "FAIL: " + what.format(*failure.subjects)

    @staticmethod
    def _refusal(failure: Failure) -> list[str]:
        subjects = failure.subjects
        if failure.kind == "parse-refused":
            return [
                f"  REFUSED ({len(subjects)} unparseable, baseline kept):",
                *(f"    {path}: parse error" for path in subjects),
            ]
        files = len({s.split(": ")[0] for s in subjects})
        return [
            f"  REFUSED ({files} files):",
            *(f"    {s} regressed" for s in subjects),
        ]
