"""The OO gate's command surface: each operation's verdict as report lines."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Self

from oo_ratchet.core.adapters.outcomelog import OutcomeLog
from oo_ratchet.core.domain.records import AuditRecord
from oo_ratchet.core.domain.verdicts import Failure, MetricRow, Verdict

HEADER = (
    f"\n{'File':<40} {'Metric':<26} {'Baseline':>10} "
    f"{'Current':>10} {'Delta':>8} {'Status':>10}"
)
LOG_HEADER = (
    f"\n{'Timestamp':<22} {'Commit':<10} {'Scored':>7} "
    f"{'Improved':>9} {'Regressed':>10} {'Verdict':>8}"
)


class OoCli:
    """Render the ``Verdict`` of one OO operation; ``baseline`` is the file's path."""

    COMMON: ClassVar[dict[str, str]] = {
        "base-unresolvable": "base ref unresolvable and --require-base is set",
        "ci-write": (
            "refusing to write baseline under GITHUB_ACTIONS without --allow-ci-write"
        ),
    }
    CHECK: ClassVar[dict[str, str]] = {
        "base-stale": (
            "cannot resolve merge-base (origin/main unfetched or stale) with an "
            "in-tree baseline present; fetch origin/main or pass --base-ref"
        ),
        "tripwire-no-baseline": (
            "--tripwire with no baseline on main; only the adoption commit "
            "that adds the baseline may bootstrap"
        ),
        "tip-unresolvable": (
            "base has no baseline and origin/main is unresolvable "
            "with an in-tree baseline present; fetch origin/main"
        ),
        "base-predates-baseline": (
            "base commit predates baseline adoption; rebase onto current main"
        ),
        "base-empty": (
            "base baseline is empty (truncated write or bad merge) "
            "and --require-base is set"
        ),
        "regression": "regression detected",
        "no-improvement": "no metric improved on any touched file",
    }
    UPDATE: ClassVar[dict[str, str]] = {
        "base-stale": (
            "cannot resolve base (origin/main unfetched or stale) with "
            "an in-tree baseline present; fetch origin/main, pass --base-ref, "
            "or use --reconcile for an intentional whole-tree sweep"
        ),
        "reconcile-no-base": (
            "cannot resolve base for reconcile (origin/main unfetched or stale) "
            "with an in-tree baseline present; fetch origin/main"
        ),
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
            "No base baseline and no origin/main -- first-adoption bootstrap pass"
        ),
        "first-adoption: no baseline at base or tip": (
            "No baseline at base or origin/main tip -- first-adoption bootstrap pass"
        ),
        "no Python files touched": "No Python files touched -- trivial pass",
    }
    FIX: ClassVar[str] = "make update-oo"
    REFUSALS: ClassVar[frozenset[str]] = frozenset({"parse-refused", "regression"})

    _baseline: Path

    def __new__(cls, baseline: Path) -> Self:
        self = super().__new__(cls)
        self._baseline = baseline
        return self

    @staticmethod
    def exit_code(verdict: Verdict) -> int:
        """Return 0 for a passing verdict, 1 for a failing one; log a refusal."""
        OutcomeLog(verdict.failures).refused()
        return 0 if verdict.passed else 1

    def check(self, verdict: Verdict) -> list[str]:
        """Return the report of a ratchet check."""
        lines: list[str] = []
        review = verdict.review
        if review is not None:
            rows = [self._row(r) for r in review.rows]
            lines += [HEADER, "-" * 108, *rows]
            if not rows:
                lines.append("  (all metrics unchanged)")
        for failure in verdict.failures:
            lines += self._check_failure(failure)
        if verdict.passed:
            lines.append(self._pass(verdict, shown=review is not None))
        return lines

    def update(self, verdict: Verdict) -> list[str]:
        """Return the report of an update or a reconcile."""
        plain = [f for f in verdict.failures if f.kind not in self.REFUSALS]
        if plain:
            return [self._failure(f, self.UPDATE) for f in plain]
        lines = [
            f"\nBaseline updated: {self._baseline}",
            f"  files improved: {verdict.improved}",
            f"  files removed:  {len(verdict.removed)}",
        ]
        for failure in verdict.failures:
            lines += self._refusal(failure)
        lines += [f"  backfilled: {path}" for path in verdict.written]
        return lines

    def relax(self, verdict: Verdict, file: str, justify: str) -> list[str]:
        """Return the report of a relax."""
        if verdict.passed:
            return [
                f"\nRelaxed {file} (reason: {justify})",
                f"  baseline: {self._baseline}",
            ]
        messages = {
            "blank-justification": "--relax requires a non-empty --justify",
            "not-scored": f"not a scored file: {file}",
            "no-row": (
                f"{file} has no baseline entry to relax; "
                "use --update or --reconcile to add a new file"
            ),
            "nothing-to-relax": (
                f"nothing to relax for {file} (no metric is worse than its baseline)"
            ),
        }
        return [self._failure(f, messages) for f in verdict.failures]

    def bless(self, verdict: Verdict, reason: str) -> list[str]:
        """Return the report of a scoped bless."""
        kinds = {f.kind for f in verdict.failures}
        if kinds - {"refused"}:
            messages = {
                "blank-reason": "--rebaseline-files requires a non-blank --reason"
            }
            return [self._failure(f, messages) for f in verdict.failures]
        accepted = verdict.written
        lines = [f"\nBaseline blessed for {len(accepted)} file(s) (reason: {reason}):"]
        lines.append("  files:" if accepted else "  (none)")
        lines += [f"    {path}" for path in accepted]
        for failure in verdict.failures:
            lines.append(
                f"  REFUSED ({len(failure.subjects)} file(s), nothing written):"
            )
            lines += [f"    {s}" for s in failure.subjects]
        return lines

    def rebaseline(self, verdict: Verdict) -> list[str]:
        """Return the report of a rebaseline."""
        if not verdict.passed:
            return [self._failure(f, {}) for f in verdict.failures]
        return [
            f"\nBaseline reset: {self._baseline}",
            f"  files scored: {len(verdict.written)}",
        ]

    @staticmethod
    def log(records: tuple[AuditRecord, ...]) -> list[str]:
        """Return the audit history as report lines."""
        lines = [LOG_HEADER, "-" * 70]
        lines.extend(
            f"{r.ts or '?':<22} {r.commit or '?':<10} {r.files_scored:>7} "
            f"{r.files_improved:>9} {r.files_regressed:>10} {r.verdict or '?':>8}"
            for r in records
        )
        return lines

    def _check_failure(self, failure: Failure) -> list[str]:
        subjects = failure.subjects
        if failure.kind == "parse-error":
            return [
                "FAIL: touched file(s) failed to parse:",
                *(f"  {s}" for s in subjects),
            ]
        if failure.kind == "missing-row":
            return [self._fix("touched file(s) not in baseline", subjects)]
        if failure.kind == "stale-row":
            return [self._fix("baseline out of date", subjects)]
        head = self._failure(Failure(failure.kind), self.CHECK)
        return [head, *(f"  {s}" for s in subjects)]

    def _fix(self, what: str, subjects: tuple[str, ...]) -> str:
        return f"FAIL: {what} -- run {self.FIX}: " + ", ".join(subjects)

    def _pass(self, verdict: Verdict, *, shown: bool) -> str:
        if shown:
            return f"PASS: {verdict.note}"
        return self.BOOTSTRAPS.get(verdict.note, verdict.note)

    def _refusal(self, failure: Failure) -> list[str]:
        subjects = failure.subjects
        if failure.kind == "parse-refused":
            return [
                f"  REFUSED ({len(subjects)} unparseable, baseline kept):",
                *(f"    {s}: parse error" for s in subjects),
            ]
        files = {s.split(": ")[0] for s in subjects}
        return [
            f"  REFUSED ({len(files)} files):",
            *(f"    {s} regressed" for s in subjects),
        ]

    def _failure(self, failure: Failure, messages: dict[str, str]) -> str:
        what = messages.get(failure.kind) or self.COMMON.get(failure.kind)
        return f"FAIL: {what or failure.kind}"

    @staticmethod
    def _row(row: MetricRow) -> str:
        return (
            f"{row.path:<40} {row.metric:<26} {row.baseline:>10} "
            f"{row.current:>10} {row.delta:>8} {row.status:>10}"
        )
