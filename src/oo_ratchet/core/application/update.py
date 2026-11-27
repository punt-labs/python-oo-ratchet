"""Update: write the baseline for the files a change touched, never loosening."""

from __future__ import annotations

from dataclasses import dataclass, field

from oo_ratchet.core.domain.records import AuditRecord
from oo_ratchet.core.domain.scores import Measurement, Rows
from oo_ratchet.core.domain.verdicts import Failure, Verdict

from .operation import Operation

Deltas = dict[str, dict[str, list[float]]]


@dataclass(frozen=True, slots=True)
class UpdatePlan:
    """Which files an update touches, plus rename, prune and broken-file intent.

    ``parse_errors`` are files on disk that failed to parse: their rows are kept
    and the update refuses, so a syntax error cannot erase a baseline row.
    ``base_rows`` is the baseline at the merge base; rows are compared against
    it as Check does, so a later commit may give back part of an earlier
    commit's gain while no worse than the base.
    """

    current: Rows
    touched: frozenset[str]
    renames: dict[str, str] = field(default_factory=dict)
    parse_errors: frozenset[str] = frozenset()
    base_rows: Rows | None = None


class Update(Operation):
    """Scope the touched files from the merge base, then apply the plan."""

    def run(
        self, *, base_ref: str | None, require_base: bool, source: str | None
    ) -> Verdict:
        """Update the rows of files in ``base..work tree``; never loosens.

        Fails closed on an unresolvable base rather than sweeping the whole
        tree. Genuine first adoption (no in-tree baseline) bootstraps it.
        """
        measured = self._source.measure()
        current = measured.metrics()
        base = self._history.resolve(base_ref)
        if base is None:
            if require_base:
                return Verdict.refused("base-unresolvable")
            if self._store.exists():
                return Verdict.refused("base-stale")
            plan = UpdatePlan(
                current, frozenset(current), parse_errors=measured.parse_errors
            )
        else:
            plan = self._scoped(base, measured)
        applier = PlanApplier(
            self._policy, self._history, self._store, self._audit, self._source
        )
        return applier.apply(plan, source)

    def _scoped(self, base: str, measured: Measurement) -> UpdatePlan:
        current = measured.metrics()
        diff = self._history.changes_since(base)
        base_rows = self._history.baseline_at(base)
        scored = current.keys() | measured.parse_errors
        stored = self._store.rows()
        touched = (
            {
                p
                for p in diff.python_files()
                if p in scored or not self._source.exists(p)
            }
            | self._vanished(stored, set(diff.renames.values()))
            | (self._policy.changed_rows(stored, base_rows or {}) & current.keys())
        )
        return UpdatePlan(
            current,
            frozenset(touched),
            diff.renames,
            parse_errors=frozenset(touched) & measured.parse_errors,
            base_rows=base_rows,
        )

    def _vanished(self, stored: Rows, carried: set[str]) -> set[str]:
        """Return rows whose file is gone, bar rename sources (the carried base)."""
        return {p for p in stored if p not in carried and not self._source.exists(p)}


class PlanApplier(Operation):
    """Write an ``UpdatePlan``, refusing per-metric regressions.

    A renamed file is compared against its predecessor's row; a refusal keeps
    that row so the carry survives to the next run; a rename source whose
    target is present is never dropped as a false deletion.
    """

    def apply(self, plan: UpdatePlan, source: str | None) -> Verdict:
        """Write the plan, append the audit record, and report."""
        stored = self._store.rows()
        rows = dict(stored)
        backfilled = sorted(
            plan.current.keys() - stored.keys() - plan.touched - plan.renames.keys()
        )
        rows.update({p: plan.current[p] for p in backfilled})
        refused: list[str] = []
        deltas: Deltas = {}
        removed: list[str] = []
        for path in sorted(plan.touched - plan.parse_errors):
            if path in plan.current:
                removed += self._write(rows, stored, plan, path, refused, deltas)
            else:
                removed += self._drop(rows, path)
        broken = sorted(plan.parse_errors)
        improved = self._improved(plan, stored, deltas)
        self._store.save(rows)
        self._audit.append(
            AuditRecord(
                verdict="pass" if not refused and not broken else "fail",
                deltas=deltas,
                files_scored=len(plan.current),
                files_improved=improved,
                files_regressed=len({r.split(": ")[0] for r in refused}) + len(broken),
                removed=tuple(sorted(removed)),
                source=source,
                commit=self._history.head(),
                extra={"backfilled": backfilled} if backfilled else {},
            )
        )
        failures = tuple(
            Failure(kind, tuple(subjects))
            for kind, subjects in (("parse-refused", broken), ("regression", refused))
            if subjects
        )
        return Verdict(
            failures=failures,
            improved=improved,
            removed=tuple(removed),
            written=tuple(backfilled) if not failures else (),
        )

    def _write(
        self,
        rows: Rows,
        stored: Rows,
        plan: UpdatePlan,
        path: str,
        refused: list[str],
        deltas: Deltas,
    ) -> list[str]:
        entry = plan.current[path]
        old = plan.renames.get(path, path)
        candidates = [
            r
            for r in ((plan.base_rows or {}), stored)
            if (r.get(path) or r.get(old)) is not None
        ]
        compared = [r.get(path) or r.get(old) or {} for r in candidates]
        worse = [set(self._policy.regressed(entry, row)) for row in compared]
        regressed = [m for m in entry if worse and all(m in w for w in worse)]
        if regressed:
            refused.extend(f"{path}: {m}" for m in regressed)
            return []
        rows[path] = entry
        changes = self._deltas(entry, compared[-1] if compared else None)
        if changes:
            deltas[path] = changes
        return self._drop(rows, plan.renames[path]) if path in plan.renames else []

    @staticmethod
    def _deltas(
        entry: dict[str, float], base: dict[str, float] | None
    ) -> dict[str, list[float]]:
        if base is None:
            return {m: [0.0, v] for m, v in entry.items()}
        return {m: [base[m], v] for m, v in entry.items() if m in base and v != base[m]}

    @staticmethod
    def _drop(rows: Rows, path: str) -> list[str]:
        if path in rows:
            del rows[path]
            return [path]
        return []

    def _improved(self, plan: UpdatePlan, stored: Rows, deltas: Deltas) -> int:
        """Count improved files among those with a prior row; a new file has none."""
        prior = stored.keys() | (plan.base_rows or {}).keys()
        return self._policy.improved_count(
            {p: d for p, d in deltas.items() if {p, plan.renames.get(p)} & prior}
        )
