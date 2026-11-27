"""Apply an update plan to the baseline: the never-loosening write mechanics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Self

from oo_ratchet.backfill import Backfill, UpdateReport

from .audit import AuditLog
from .baseline import Baseline
from .gitio import GitRepo
from .outcome import Outcome
from .thresholds import Thresholds


@dataclass(frozen=True, slots=True)
class UpdatePlan:
    """Which files an update touches, plus rename, prune, and broken-file intent.

    ``parse_errors`` are paths on disk that failed to AST-parse. They must be
    preserved (never pruned as if deleted) and surfaced as a refusal, so a
    syntax error cannot silently erase a file's baseline history.

    ``base_baseline`` is the baseline committed at the merge base. When
    present, rows are compared against it, as ``check`` does, so a later
    commit on a branch is never refused for giving back part of an earlier
    commit's gain while still being no worse than the base (PL-1685).
    """

    current: dict[str, dict[str, float]]
    touched: frozenset[str]
    renames: dict[str, str] = field(default_factory=dict)
    prune: bool = False
    parse_errors: frozenset[str] = frozenset()
    base_baseline: dict[str, dict[str, float]] | None = None


class PlanApplier:
    """Write an ``UpdatePlan`` to the baseline, refusing per-metric regressions.

    A renamed file is compared against its predecessor's carried entry (S8); a
    refusal keeps that entry so the carry survives to the next run; a rename
    source whose target is present is never pruned as a false deletion.
    """

    _baseline: Baseline
    _audit: AuditLog
    _git: GitRepo

    def __new__(cls, baseline: Baseline, audit: AuditLog, git: GitRepo) -> Self:
        self = super().__new__(cls)
        self._baseline = baseline
        self._audit = audit
        self._git = git
        return self

    def apply(self, plan: UpdatePlan, source: str | None) -> Outcome:
        """Apply the plan, save the baseline, append the audit, and report."""
        new_baseline = dict(self._baseline.entries)
        backfill = Backfill(plan.current, new_baseline, plan.touched, plan.renames)
        backfill.apply(new_baseline)
        refused: list[tuple[str, str]] = []
        deltas: dict[str, dict[str, list[float]]] = {}
        removed: list[str] = []
        for path in sorted(plan.touched):
            if path in plan.parse_errors:
                continue  # on disk but unparseable: keep its row, refuse below
            if path not in plan.current:
                removed += self._drop(new_baseline, path)
                continue
            removed += self._write_or_refuse(new_baseline, plan, path, refused, deltas)
        if plan.prune:
            removed += self._prune_kept(new_baseline, plan)
        broken = sorted(plan.parse_errors)
        improved = self._improved_files(plan, deltas)
        self._baseline.save(new_baseline)
        self._audit.append(
            files_scored=len(plan.current),
            files_improved=improved,
            files_regressed=len({p for p, _ in refused}) + len(broken),
            verdict="pass" if not refused and not broken else "fail",
            deltas=deltas,
            removed=removed,
            source=source,
            commit=self._git.short_head(),
            **backfill.metadata,
        )
        outcome = self._report(improved, len(removed), refused, broken)
        return Outcome(
            outcome.exit_code, outcome.lines + backfill.lines(outcome.exit_code)
        )

    def _write_or_refuse(
        self,
        new_baseline: dict[str, dict[str, float]],
        plan: UpdatePlan,
        path: str,
        refused: list[tuple[str, str]],
        deltas: dict[str, dict[str, list[float]]],
    ) -> list[str]:
        entry = plan.current[path]
        rows = self._comparison_rows(plan, path)
        # Deltas record what this write changes: against the in-tree row (last)
        # when there is one, so a rerun does not re-record the same gain.
        base_entry = rows[-1] if rows else None
        regressed = self.refusals(entry, rows)
        if regressed:
            # Keep the old rename-source entry so the carried base survives to
            # the next run -- dropping it would let a later run treat the rename
            # as a brand-new file and launder the regression.
            refused.extend((path, m) for m in regressed)
            return []
        new_baseline[path] = entry
        file_deltas = self.deltas(entry, base_entry)
        if file_deltas:
            deltas[path] = file_deltas
        return self._drop_rename_source(new_baseline, plan, path)

    def _comparison_rows(self, plan: UpdatePlan, path: str) -> list[dict[str, float]]:
        """Return the merge-base row, then the in-tree row, for ``path``.

        A rename target falls back to its source's row in each baseline.
        """
        sources = [plan.base_baseline or {}, self._baseline.entries]
        old = plan.renames.get(path, path)
        found = (rows.get(path) or rows.get(old) for rows in sources)
        return [row for row in found if row is not None]

    @classmethod
    def refusals(
        cls, entry: dict[str, float], rows: list[dict[str, float]]
    ) -> list[str]:
        """Return the metrics worse than every comparison row.

        The merge-base row is what ``check`` enforces; the in-tree row may
        hold an audited relaxation made earlier on the branch. A metric no
        worse than either is accepted, and ``check`` still rejects a
        regression against the merge base that no relaxation waives.
        """
        if not rows:
            return []
        worse = [set(cls.regressed(entry, row)) for row in rows]
        return [m for m in entry if all(m in w for w in worse)]

    def _drop_rename_source(
        self, new_baseline: dict[str, dict[str, float]], plan: UpdatePlan, path: str
    ) -> list[str]:
        old = plan.renames.get(path)
        if old is not None:
            return self._drop(new_baseline, old)
        return []

    @staticmethod
    def _drop(new_baseline: dict[str, dict[str, float]], path: str) -> list[str]:
        if path in new_baseline:
            del new_baseline[path]
            return [path]
        return []

    @staticmethod
    def _prune_kept(
        new_baseline: dict[str, dict[str, float]], plan: UpdatePlan
    ) -> list[str]:
        # Prune only genuine deletions. A file present on disk is either
        # parse-clean (in ``current``) or a parse error; a rename source is kept
        # whenever its target is present on disk at all -- parseable or not --
        # so a rename to an unparseable target never drops the old row.
        present = plan.current.keys() | plan.parse_errors
        rename_sources = frozenset(
            old for new, old in plan.renames.items() if new in present
        )
        kept = present | rename_sources
        stale = [p for p in new_baseline if p not in kept]
        for p in stale:
            del new_baseline[p]
        return stale

    def _improved_files(
        self, plan: UpdatePlan, deltas: dict[str, dict[str, list[float]]]
    ) -> int:
        """Count improved files among those with a prior row; a new file has none."""
        prior = self._baseline.entries.keys() | (plan.base_baseline or {}).keys()
        return self.improved_count(
            {p: d for p, d in deltas.items() if plan.renames.get(p, p) in prior}
        )

    @staticmethod
    def improved_count(deltas: dict[str, dict[str, list[float]]]) -> int:
        """Return how many files have a metric strictly better than before.

        A changed value is not necessarily better: ``module_size`` growing
        under its ceiling is recorded but is neither better nor worse.
        """
        return sum(
            any(
                Thresholds.strictly_better(metric, new, old)
                for metric, (old, new) in changes.items()
            )
            for changes in deltas.values()
        )

    @staticmethod
    def regressed(entry: dict[str, float], base: dict[str, float] | None) -> list[str]:
        """Return the metrics in ``entry`` worse than ``base`` (empty if new).

        A metric missing from ``base`` is judged by its target, never skipped.
        """
        if base is None:
            return []
        return [
            m
            for m in entry
            if not (
                Thresholds.better_or_equal(m, entry[m], base[m])
                if m in base
                else Thresholds.meets(m, entry[m])
            )
        ]

    @staticmethod
    def over_cap_and_regressed(
        entry: dict[str, float], base: dict[str, float] | None
    ) -> list[str]:
        """Return the metrics that refuse a ``--rebaseline-files`` bless.

        A metric refuses the bless only when it BOTH fails its absolute
        ``Thresholds.meets`` cap AND regressed against ``base`` (worse than
        the file's existing committed baseline value for that metric, per
        ``Thresholds.better_or_equal`` -- direction-aware, so a floor metric
        like ``encapsulation_ratio`` regresses on a DECREASE while a cap
        metric like ``avg_params`` regresses on an INCREASE). An over-cap metric
        that is unchanged or improved against its baseline is carried
        forward untouched, not refused -- ``check()``'s own lock/
        no-regression rule already grandfathers a pre-existing,
        non-regressing violation; refusing it again here would let one
        already-accepted debt on a file block an unrelated,
        genuinely-necessary within-cap regression on the SAME file.

        ``base`` absent (a genuinely new file, never rebaselined before) or
        missing this specific metric falls back to the strict rule: any
        value over cap refuses -- there is no prior value to grandfather
        against.
        """
        refusals: list[str] = []
        for metric, value in entry.items():
            if Thresholds.meets(metric, value):
                continue
            if base is None or metric not in base:
                refusals.append(metric)
                continue
            if not Thresholds.better_or_equal(metric, value, base[metric]):
                refusals.append(metric)
        return refusals

    @staticmethod
    def deltas(
        entry: dict[str, float], base: dict[str, float] | None
    ) -> dict[str, list[float]]:
        """Return the changed metrics as ``{metric: [old, new]}``."""
        if base is None:
            return {m: [0.0, entry[m]] for m in entry}
        return {
            m: [base[m], entry[m]] for m in entry if m in base and entry[m] != base[m]
        }

    def _report(
        self,
        improved: int,
        removed: int,
        refused: list[tuple[str, str]],
        broken: list[str],
    ) -> Outcome:
        report = UpdateReport(self._baseline.path, improved, removed)
        report.refuse(refused, broken)
        return Outcome(report.exit_code, report.lines)
