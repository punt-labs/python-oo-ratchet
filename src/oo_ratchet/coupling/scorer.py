"""Score a file or directory of modules for coupling and cohesion."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING, Self

from .config import CouplingConfig
from .imports import ImportResolver
from .metrics import ModuleCouplingMetrics
from .packages import PackageMetrics
from .thresholds import COUPLING_METRICS, MAX_AGGREGATED, CouplingTargets
from .tree import CouplingTree

if TYPE_CHECKING:
    from oo_ratchet.source_set import Source


class CouplingScorer:
    """Score modules against coupling/cohesion thresholds.

    Keys are normalized repo-relative (POSIX) against ``repo_root`` so scorer
    output, baseline keys, and git-diff paths all intersect cleanly regardless
    of how the target path was spelled on the command line.
    """

    _results: list[dict[str, float | int | str]]
    _packages: tuple[PackageMetrics, ...]
    _config: CouplingConfig

    def __new__(
        cls,
        target: Source,
        repo_root: Path | None = None,
        config: CouplingConfig | None = None,
    ) -> Self:
        self = super().__new__(cls)
        root = repo_root if repo_root is not None else Path.cwd()
        self._config = config if config is not None else CouplingConfig()
        tree = CouplingTree(target)
        cycle = tree.cycles
        self._results = [self._safe_score(f, tree, cycle, root) for f in tree.files]
        self._packages = tree.packages
        return self

    @property
    def results(self) -> list[dict[str, float | int | str]]:
        """Return the per-file metric dicts."""
        return self._results

    @property
    def config(self) -> CouplingConfig:
        """Return the repository coupling settings this scorer applied."""
        return self._config

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
        return self._aggregate()

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
        targets = CouplingTargets(self._config.caps)
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
            bucket = capped if metric in self._config.caps.get(path, {}) else rest
            bucket.append((path, float(r[metric])))
        return capped, rest

    @property
    def fail_count(self) -> int:
        """Return the number of aggregated metrics failing their threshold."""
        return sum(1 for g in self.grades.values() if g == "FAIL")

    def _safe_score(
        self,
        py_file: Path,
        scope: CouplingTree,
        cycle: frozenset[str],
        root: Path,
    ) -> dict[str, float | int | str]:
        key = self._normalize(py_file, root)
        try:
            tree = ast.parse(py_file.read_text(), filename=str(py_file))
        except (SyntaxError, OSError, UnicodeDecodeError) as exc:
            # A file that cannot be read or decoded is scored as an error, like a
            # syntax error: the ratchet fails on it if it is a touched file
            # (fail-closed), rather than crashing the whole scoring pass.
            return {"file": key, "error": str(exc)}
        mod_key = scope.source.key_for(py_file)
        resolver = ImportResolver(
            mod_key,
            scope.modules,
            scope.source.name,
            is_package=py_file.name == "__init__.py",
        )
        metrics = ModuleCouplingMetrics(
            key, tree, resolver, self._config.stateless_values
        ).compute()
        metrics["circular_imports"] = 1 if mod_key in cycle else 0
        return metrics

    @staticmethod
    def _normalize(path: Path, root: Path) -> str:
        resolved = path.resolve()
        try:
            return resolved.relative_to(root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()

    def _aggregate(self) -> dict[str, float]:
        agg: dict[str, list[float]] = {k: [] for k in COUPLING_METRICS.names}
        for r in self._results:
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
