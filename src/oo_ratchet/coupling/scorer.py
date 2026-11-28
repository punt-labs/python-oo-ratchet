"""Aggregate scored coupling rows into a summary and PASS/FAIL grades."""

from __future__ import annotations

from typing import Self

from .packages import PackageMetrics
from .thresholds import COUPLING_METRICS, MAX_AGGREGATED, CouplingTargets


class CouplingScorer:
    """Summarize per-file coupling rows against coupling/cohesion thresholds.

    The rows are already scored (keys normalized repo-relative POSIX by the
    adapter that read the files), so this class holds no path and does no IO.
    """

    _results: list[dict[str, float | int | str]]
    _packages: tuple[PackageMetrics, ...]
    _caps: dict[str, dict[str, float]]

    def __new__(
        cls,
        results: list[dict[str, float | int | str]],
        packages: tuple[PackageMetrics, ...],
        caps: dict[str, dict[str, float]] | None = None,
    ) -> Self:
        self = super().__new__(cls)
        self._results = results
        self._packages = packages
        self._caps = caps if caps is not None else {}
        return self

    @property
    def results(self) -> list[dict[str, float | int | str]]:
        """Return the per-file metric dicts."""
        return self._results

    @property
    def targets(self) -> CouplingTargets:
        """Return the targets each file is judged against, under its caps."""
        return CouplingTargets(self._caps)

    @property
    def packages(self) -> tuple[PackageMetrics, ...]:
        """Return the per-sub-package metrics."""
        return self._packages

    @property
    def files(self) -> frozenset[str]:
        """Return the repo-relative paths the scorer enumerated (parse-clean)."""
        return frozenset(str(r["file"]) for r in self._results if "error" not in r)

    @property
    def parse_errors(self) -> frozenset[str]:
        """Return the paths that failed to AST-parse (excluded from scoring)."""
        return frozenset(str(r["file"]) for r in self._results if "error" in r)

    @property
    def summary(self) -> dict[str, float]:
        """Return the aggregated metric summary across all scored files."""
        return self._aggregate(self._results)

    @property
    def grades(self) -> dict[str, str]:
        """Return PASS/FAIL per aggregated metric.

        A file with a configured cap for a metric is judged against that cap.
        Otherwise a max-aggregated metric passes only if every file meets its
        own target (``__main__`` relaxation included), and an averaged metric
        compares the mean of the uncapped files with the strict table.
        """
        return {
            k: "PASS" if self._passes(k, v) else "FAIL" for k, v in self.summary.items()
        }

    def _passes(self, metric: str, value: float) -> bool:
        targets = self.targets
        capped, rest = self._split_capped(metric)
        if not all(targets.metric(metric, f).meets(v) for f, v in capped):
            return False
        if metric in MAX_AGGREGATED:
            return all(targets.metric(metric, f).meets(v) for f, v in rest)
        if capped and rest:
            value = round(sum(v for _, v in rest) / len(rest), 3)
        return not rest or targets.metric(metric).meets(value)

    def _split_capped(
        self, metric: str
    ) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
        """Split scored ``(file, value)`` rows into capped and uncapped."""
        capped: list[tuple[str, float]] = []
        rest: list[tuple[str, float]] = []
        for r in self._results:
            if "error" in r or metric not in r:
                continue
            path = str(r["file"])
            bucket = capped if metric in self._caps.get(path, {}) else rest
            bucket.append((path, float(r[metric])))
        return capped, rest

    @property
    def fail_count(self) -> int:
        """Return the number of aggregated metrics failing their threshold."""
        return sum(1 for g in self.grades.values() if g == "FAIL")

    @staticmethod
    def _aggregate(results: list[dict[str, float | int | str]]) -> dict[str, float]:
        agg: dict[str, list[float]] = {k: [] for k in COUPLING_METRICS.names}
        for r in results:
            if "error" in r:
                continue
            for k in COUPLING_METRICS.names:
                if k in r:
                    agg[k].append(float(r[k]))
        summary: dict[str, float] = {}
        for k, values in agg.items():
            if not values:
                continue
            if k in MAX_AGGREGATED:
                summary[k] = max(values)
            else:
                summary[k] = round(sum(values) / len(values), 3)
        return summary
