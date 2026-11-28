"""Aggregate, grade and render per-module OO metric results (pure data)."""

from __future__ import annotations

from typing import Self

from .thresholds import OO_METRICS

# Metrics whose aggregate is the worst (max) rather than the mean.
_MAX_AGGREGATED = frozenset(
    {
        "max_complexity",
        "module_size",
        "init_violations",
        "public_attr_violations",
    }
)
# Metrics whose aggregate is the worst (min) rather than the mean.
_MIN_AGGREGATED = frozenset({"future_annotations"})


class Scoring:
    """Aggregate and render per-module OO metric results against thresholds.

    Takes the per-file metric dicts (or ``{"file", "error"}`` rows for modules
    that failed to parse) as data; it reads no files. ``Scorer`` in ``.tree``
    produces those dicts from a source tree.
    """

    _results: list[dict[str, float | int | str]]

    def __new__(cls, results: list[dict[str, float | int | str]]) -> Self:
        self = super().__new__(cls)
        self._results = results
        return self

    @property
    def results(self) -> list[dict[str, float | int | str]]:
        """Return the per-file metric dicts."""
        return self._results

    @property
    def rows(self) -> dict[str, dict[str, float]]:
        """Return each parsed file's gated metric values, keyed by path."""
        return {
            str(r["file"]): {k: float(r[k]) for k in OO_METRICS.names if k in r}
            for r in self._results
            if "error" not in r
        }

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
        """Return PASS/FAIL per aggregated metric."""
        return {
            k: "PASS" if OO_METRICS.metric(k).meets(v) else "FAIL"
            for k, v in self.summary.items()
        }

    @property
    def fail_count(self) -> int:
        """Return the number of aggregated metrics that fail their threshold."""
        return sum(1 for g in self.grades.values() if g == "FAIL")

    def _aggregate(self) -> dict[str, float]:
        parsed = [r for r in self._results if "error" not in r]
        columns = {k: [float(r[k]) for r in parsed if k in r] for k in OO_METRICS.names}
        return {k: self._reduce(k, v) for k, v in columns.items() if v}

    @staticmethod
    def _reduce(name: str, values: list[float]) -> float:
        if name in _MAX_AGGREGATED:
            return max(values)
        if name in _MIN_AGGREGATED:
            return min(values)
        return round(sum(values) / len(values), 3)

    def render_table(self) -> list[str]:
        """Return the aggregate metric table as report lines."""
        summary = self.summary
        grades = self.grades
        lines = [
            f"\n{'Metric':<28} {'Value':>8} {'Target':>10} {'Grade':>6}",
            "-" * 56,
        ]
        for k in OO_METRICS.names:
            if k not in summary:
                continue
            metric = OO_METRICS.metric(k)
            op, target_val = metric.op, metric.target
            g = grades[k]
            marker = "  " if g == "PASS" else " *"
            lines.append(f"{k:<28} {summary[k]:>8.2f} {op} {target_val:<8} {g}{marker}")
        return lines

    def render_per_file(self) -> list[str]:
        """Return the per-file metric breakdown as report lines."""
        lines = ["\n--- Per-file breakdown ---"]
        for r in self._results:
            lines.append(f"\n  {r.get('file', '?')}")
            for k, v in r.items():
                if k == "file" or k not in OO_METRICS:
                    continue
                g = "PASS" if OO_METRICS.metric(k).meets(float(v)) else "FAIL"
                lines.append(f"    {k:<26} {v:>8} {g}")
        return lines

    def report(self) -> dict[str, object]:
        """Return per-file, aggregate, grades, and thresholds as a mapping."""
        return {
            "per_file": self._results,
            "aggregate": self.summary,
            "grades": self.grades,
            "thresholds": {m.name: m.describe() for m in OO_METRICS.items},
        }
