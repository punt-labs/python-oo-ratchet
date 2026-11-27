"""Check: judge a change against the baseline committed at the merge base."""

from __future__ import annotations

from oo_ratchet.core.domain.records import AuditRecord
from oo_ratchet.core.domain.scores import Measurement, Rows
from oo_ratchet.core.domain.verdicts import Failure, Review, Verdict

from .bases import Bases
from .operation import Operation


class Check(Operation):
    """Compare touched files at HEAD against the base baseline.

    The comparison rows come from the base commit, never the in-tree file, so
    a change may improve code and lock in its own baseline in one commit.
    """

    def run(
        self,
        *,
        base_ref: str | None,
        require_base: bool,
        allow_no_improvement: bool = False,
        tripwire: bool = False,
    ) -> Verdict:
        """Return the verdict for the change from the base to the work tree."""
        bases = Bases(
            self._history.resolve,
            lambda tip: self._history.baseline_at(tip) is not None,
            self._store.exists,
        )
        base = self._history.resolve(base_ref)
        if base is None:
            return bases.unresolved(require_base=require_base)
        base_rows = self._history.baseline_at(base)
        if base_rows is None:
            return bases.undocumented(tripwire=tripwire)
        if not base_rows and require_base:
            return Verdict.refused("base-empty")
        return self._judge(base, base_rows, allow_no_improvement=allow_no_improvement)

    def _judge(
        self, base: str, base_rows: Rows, *, allow_no_improvement: bool
    ) -> Verdict:
        diff = self._history.changes_since(base)
        measured = self._source.measure()
        touched_py = diff.python_files()
        broken = sorted(touched_py & measured.parse_errors)
        if broken:
            return Verdict(failures=(Failure("parse-error", tuple(broken)),))
        current = measured.metrics()
        touched = sorted(touched_py & measured.paths)
        rewritten = self._rewritten(base_rows, measured, touched)
        if not touched:
            return self._untouched(rewritten, current)
        waivers = AuditRecord.waivers_since(
            self._audit.records(), self._history.audit_at(base)
        )
        stored = self._store.rows()
        review = Review(
            tuple(
                self._policy.review(
                    p,
                    current[p],
                    self._base_row(base_rows, diff.renames, p),
                    stored.get(p),
                    waivers,
                )
                for p in touched
            )
        )
        failures = self._integrity([*touched, *rewritten], current)
        return self._verdict(
            review, failures, allow_no_improvement=allow_no_improvement
        )

    @staticmethod
    def _base_row(
        base_rows: Rows, renames: dict[str, str], path: str
    ) -> dict[str, float] | None:
        row = base_rows.get(path)
        if row is None and path in renames:
            row = base_rows.get(renames[path])
        return row

    def _rewritten(
        self, base_rows: Rows, measured: Measurement, touched: list[str]
    ) -> list[str]:
        """Rows the branch rewrote for files no longer in the diff (a revert)."""
        if not self._policy.lock_rows:
            return []
        changed = self._policy.changed_rows(self._store.rows(), base_rows)
        return sorted((changed & measured.paths) - set(touched))

    def _untouched(self, rewritten: list[str], current: Rows) -> Verdict:
        if not self._policy.lock_rows:
            return Verdict.ok("no scored Python files touched")
        stale = self._integrity(rewritten, current)
        if stale:
            return Verdict(failures=stale)
        return Verdict.ok("no Python files touched")

    def _integrity(self, paths: list[str], current: Rows) -> tuple[Failure, ...]:
        if not self._policy.lock_rows:
            return ()
        stored = self._store.rows()
        missing = [p for p in paths if p not in stored]
        stale = [
            p
            for p in paths
            if p in stored and not self._policy.locked(stored[p], current[p])
        ]
        found = (("missing-row", missing), ("stale-row", stale))
        return tuple(Failure(kind, tuple(ps)) for kind, ps in found if ps)

    def _verdict(
        self,
        review: Review,
        integrity: tuple[Failure, ...],
        *,
        allow_no_improvement: bool,
    ) -> Verdict:
        failures = list(integrity)
        if review.has_regression:
            subjects = tuple(f"{p}: {m}" for p, m in review.regressions)
            failures.append(Failure("regression", subjects))
        gated = self._policy.must_improve and not allow_no_improvement
        if gated and not review.improvement_satisfied:
            failures.append(Failure("no-improvement"))
        note = self._pass_note(review, allow_no_improvement=allow_no_improvement)
        return Verdict(failures=tuple(failures), note=note, review=review)

    def _pass_note(self, review: Review, *, allow_no_improvement: bool) -> str:
        if not self._policy.must_improve:
            return "no regressions"
        if allow_no_improvement and not review.improvement_satisfied:
            return "no regressions (must-improve gate waived)"
        return "at least one metric improved, no regressions"
