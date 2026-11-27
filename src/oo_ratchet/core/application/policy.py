"""The per-gate comparison policy: the only thing that differs between gates."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace

from oo_ratchet.core.domain.metrics import Metric
from oo_ratchet.core.domain.verdicts import FileReview, MetricRow, Waiver

from .pathtargets import PathTargets

Row = Mapping[str, float]


@dataclass(frozen=True, slots=True)
class GatePolicy:
    """Which metrics a gate tracks and how two scores compare.

    ``must_improve``: a change must improve a metric on a touched file.
    ``absolute_targets``: a new file, and a metric missing from a base row, is
    judged by the metric's target; otherwise it is only informational.
    ``lock_rows``: the in-tree baseline must equal the scores of every touched
    or rewritten file.
    ``in_tree_only``: an update compares with the in-tree rows alone and never
    reads the merge-base baseline, and counts every file it writes a delta for
    as improved, a new file included.
    ``detailed_refusals``: a refused bless names each metric's value and the
    target it broke.
    ``targets``: per-file replacements for a metric's target (see
    ``for_path``).
    """

    metrics: tuple[Metric, ...]
    must_improve: bool = True
    absolute_targets: bool = True
    lock_rows: bool = True
    in_tree_only: bool = False
    detailed_refusals: bool = False
    targets: PathTargets = field(default_factory=PathTargets)

    @classmethod
    def from_table(
        cls,
        table: Mapping[str, tuple[str, float]],
        ceilings: Collection[str] = (),
        *,
        must_improve: bool = True,
        absolute_targets: bool = True,
        lock_rows: bool = True,
    ) -> GatePolicy:
        """Build a policy from an ``{name: (op, target)}`` table."""
        metrics = tuple(
            Metric(name, op, target, name in ceilings)
            for name, (op, target) in table.items()
        )
        return cls(metrics, must_improve, absolute_targets, lock_rows)

    @property
    def names(self) -> tuple[str, ...]:
        """Return the tracked metric names in table order."""
        return tuple(m.name for m in self.metrics)

    def metric(self, name: str) -> Metric:
        """Return the named metric."""
        return next(m for m in self.metrics if m.name == name)

    def for_path(self, path: str) -> GatePolicy:
        """Return this policy with ``path``'s own targets, as it is judged."""
        if not self.targets.names(path):
            return self
        metrics = self.targets.metrics_for(path, self.metrics)
        return replace(self, metrics=metrics, targets=PathTargets())

    def changed_rows(
        self, rows: Mapping[str, Row], base: Mapping[str, Row]
    ) -> set[str]:
        """Return paths whose tracked values differ between ``rows`` and ``base``."""
        return {
            path
            for path, row in rows.items()
            if path in base and any(row.get(m) != base[path].get(m) for m in self.names)
        }

    def locked(self, intree: Row, current: Row) -> bool:
        """Return whether the in-tree row equals the current scores."""
        return all(intree.get(m) == current.get(m) for m in self.names if m in current)

    def regressed(self, entry: Row, base: Row | None) -> list[str]:
        """Return the metrics of ``entry`` worse than ``base`` (none if new).

        A metric missing from ``base`` is judged by its target, never skipped.
        """
        if base is None:
            return []
        return [m for m in entry if self._worse(m, entry[m], base)]

    def refusals(self, entry: Row, rows: Sequence[Row]) -> list[str]:
        """Return the metrics worse than every comparison row.

        The merge-base row is what Check enforces; the in-tree row may hold an
        audited relaxation made earlier on the branch. A metric no worse than
        either is accepted.
        """
        worse = [set(self.regressed(entry, row)) for row in rows]
        return [m for m in entry if worse and all(m in w for w in worse)]

    def loosened(self, entry: Row, recorded: Row) -> list[str]:
        """Return the recorded metrics ``entry`` is worse on: the waivable ones."""
        return [m for m in self.regressed(entry, recorded) if m in recorded]

    @staticmethod
    def deltas(entry: Row, base: Row | None) -> dict[str, list[float]]:
        """Return the changed metrics as ``{metric: [old, new]}``; all if new."""
        if base is None:
            return {m: [0.0, v] for m, v in entry.items()}
        return {m: [base[m], v] for m, v in entry.items() if m in base and v != base[m]}

    def changes(
        self, entry: Row, old: Row
    ) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
        """Split the changed metrics into (worse, strictly better) deltas."""
        worse: dict[str, list[float]] = {}
        better: dict[str, list[float]] = {}
        for m, pair in self.deltas(entry, old).items():
            metric = self.metric(m)
            if not metric.better_or_equal(pair[1], pair[0]):
                worse[m] = pair
            elif metric.strictly_better(pair[1], pair[0]):
                better[m] = pair
        return worse, better

    def over_cap_and_regressed(self, entry: Row, base: Row | None) -> list[str]:
        """Return the metrics that refuse a scoped bless.

        A metric refuses only when it fails its target AND is worse than the
        recorded row. With no recorded value, failing the target refuses.
        """
        return [
            m
            for m, value in entry.items()
            if not self.metric(m).meets(value)
            and (base is None or m not in base or self._worse(m, value, base))
        ]

    def refusal(self, entry: Row, gated: Sequence[str]) -> str:
        """Return why a bless refused the metrics ``gated``."""
        if not self.detailed_refusals:
            return f"{', '.join(gated)} over cap and regressed"
        return "; ".join(
            f"{m}={entry[m]:g} fails {self.metric(m).op} "
            f"{self.metric(m).target:g} (over cap and regressed)"
            for m in gated
        )

    def improved_count(self, deltas: Mapping[str, Mapping[str, list[float]]]) -> int:
        """Return the files with a metric strictly better than before."""
        return sum(
            any(self.metric(m).strictly_better(new, old) for m, (old, new) in d.items())
            for d in deltas.values()
        )

    def strictly_better(self, metric: str, current: float, base: float) -> bool:
        """Return whether ``current`` strictly beats ``base``."""
        return self.metric(metric).strictly_better(current, base)

    def review(
        self,
        path: str,
        current: Row,
        base: Row | None,
        intree: Row | None,
        waivers: Collection[Waiver],
    ) -> FileReview:
        """Judge one touched file against its base row."""
        if base is None:
            return self._review_new(path, current)
        return self._review_tracked(path, current, base, intree, waivers)

    def _review_new(self, path: str, current: Row) -> FileReview:
        rows: list[MetricRow] = []
        failed: list[str] = []
        for m in self.metrics:
            if m.name not in current:
                continue
            val = current[m.name]
            if not self.absolute_targets:
                status = "INFO"
            else:
                status = "PASS" if m.meets(val) else "FAIL"
            if status == "FAIL":
                failed.append(m.name)
            rows.append(MetricRow(path, m.name, "NEW", f"{val:.3f}", "--", status))
        return FileReview(
            path,
            tuple(rows),
            tuple(failed),
            new_passes=self.absolute_targets and not failed,
        )

    def _review_tracked(
        self,
        path: str,
        current: Row,
        base: Row,
        intree: Row | None,
        waivers: Collection[Waiver],
    ) -> FileReview:
        rows: list[MetricRow] = []
        by_status: dict[str, list[str]] = {}
        for m in self.metrics:
            if m.name not in current or (
                m.name not in base and not self.absolute_targets
            ):
                continue
            cur = current[m.name]
            locked = intree is not None and intree.get(m.name) == cur
            waived = locked and Waiver(path, m.name) in waivers
            status = self._classify(m, cur, base, waived=waived)
            by_status.setdefault(status, []).append(m.name)
            base_val = base.get(m.name, cur)
            delta = cur - base_val
            if delta != 0.0 or status in ("REGRESSED", "RELAXED"):
                rows.append(
                    MetricRow(
                        path,
                        m.name,
                        f"{base_val:.3f}",
                        f"{cur:.3f}",
                        f"{delta:+.3f}",
                        status,
                    )
                )
        return FileReview(
            path,
            tuple(rows),
            tuple(by_status.get("REGRESSED", ())),
            tuple(by_status.get("RELAXED", ())),
            improved=bool(by_status.get("IMPROVED")),
            base_present=True,
        )

    @staticmethod
    def _classify(m: Metric, cur: float, base: Row, *, waived: bool) -> str:
        if m.name not in base:
            # Judged by its target: a hand-edited row cannot hide a regression
            # or earn must-improve credit.
            return "PASS" if m.meets(cur) else "REGRESSED"
        if m.strictly_better(cur, base[m.name]):
            return "IMPROVED"
        if m.better_or_equal(cur, base[m.name]):
            return "PASS"
        return "RELAXED" if waived else "REGRESSED"

    def _worse(self, name: str, value: float, base: Row) -> bool:
        m = self.metric(name)
        if name in base:
            return not m.better_or_equal(value, base[name])
        return self.absolute_targets and not m.meets(value)

    def unknown(self, names: Iterable[str]) -> list[str]:
        """Return the names that are not tracked metrics."""
        return [n for n in names if n not in self.names]
