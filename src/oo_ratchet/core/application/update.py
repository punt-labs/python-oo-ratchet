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
        return PlanApplier(self._policy, self._ports).apply(plan, source)

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


@dataclass(slots=True)
class Tally:
    """What one update run has done so far: rows, refusals, deltas, removals."""

    rows: Rows
    refused: list[str] = field(default_factory=list)
    deltas: Deltas = field(default_factory=dict)
    removed: list[str] = field(default_factory=list)


class PlanApplier(Operation):
    """Write an ``UpdatePlan``, refusing per-metric regressions.

    A renamed file is compared against its predecessor's row; a refusal keeps
    that row so the carry survives to the next run; a rename source whose
    target is present is never dropped as a false deletion.
    """

    def apply(self, plan: UpdatePlan, source: str | None) -> Verdict:
        """Write the plan, append the audit record, and report."""
        stored = self._store.rows()
        tally = Tally(dict(stored))
        backfilled = sorted(
            plan.current.keys() - stored.keys() - plan.touched - plan.renames.keys()
        )
        tally.rows.update({p: plan.current[p] for p in backfilled})
        for path in sorted(plan.touched - plan.parse_errors):
            if path in plan.current:
                self._write(plan, stored, tally, path)
            else:
                tally.removed += self._drop(tally.rows, path)
        broken = sorted(plan.parse_errors)
        improved = self._improved(plan, stored, tally.deltas)
        self._store.save(tally.rows)
        record = self._record(plan, tally, (improved, broken, backfilled), source)
        self._audit.append(record)
        failures = tuple(
            Failure(kind, tuple(subjects))
            for kind, subjects in (
                ("parse-refused", broken),
                ("regression", tally.refused),
            )
            if subjects
        )
        return Verdict(
            failures=failures,
            improved=improved,
            removed=tuple(tally.removed),
            written=tuple(backfilled) if not failures else (),
        )

    def _record(
        self,
        plan: UpdatePlan,
        tally: Tally,
        found: tuple[int, list[str], list[str]],
        source: str | None,
    ) -> AuditRecord:
        improved, broken, backfilled = found
        refused_files = {r.split(": ")[0] for r in tally.refused}
        return AuditRecord(
            verdict="pass" if not tally.refused and not broken else "fail",
            deltas=tally.deltas,
            files_scored=len(plan.current),
            files_improved=improved,
            files_regressed=len(refused_files) + len(broken),
            removed=tuple(sorted(tally.removed)),
            source=source,
            commit=self._history.head(),
            extra={"backfilled": backfilled} if backfilled else {},
        )

    def _write(self, plan: UpdatePlan, stored: Rows, tally: Tally, path: str) -> None:
        entry = plan.current[path]
        compared = self._comparison_rows(plan, stored, path)
        regressed = self._policy.refusals(entry, compared)
        if regressed:
            # Keep the rename source's row so the carry survives to the next run.
            tally.refused.extend(f"{path}: {m}" for m in regressed)
            return
        tally.rows[path] = entry
        changes = self._policy.deltas(entry, compared[-1] if compared else None)
        if changes:
            tally.deltas[path] = changes
        if path in plan.renames:
            tally.removed += self._drop(tally.rows, plan.renames[path])

    @staticmethod
    def _comparison_rows(
        plan: UpdatePlan, stored: Rows, path: str
    ) -> list[dict[str, float]]:
        """Return the merge-base row, then the in-tree row; a rename uses its source."""
        old = plan.renames.get(path, path)
        sources = (plan.base_rows or {}, stored)
        found = ((rows.get(path) or rows.get(old)) for rows in sources)
        return [row for row in found if row is not None]

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
