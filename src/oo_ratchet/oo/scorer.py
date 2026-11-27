"""Score a file or directory of modules and aggregate the results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Self

from oo_ratchet.source_set import Source, SourceSelection

from .metrics import ModuleMetrics
from .thresholds import Thresholds

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


class Scorer:
    """Score modules against OO quality thresholds.

    Keys are normalized repo-relative (POSIX) against ``repo_root`` so that
    scorer output, baseline keys, and git diff paths all intersect cleanly
    regardless of how the target path was spelled on the command line.
    """

    _results: list[dict[str, float | int | str]]

    def __new__(cls, target: Source, repo_root: Path | None = None) -> Self:
        self = super().__new__(cls)
        root = repo_root if repo_root is not None else Path.cwd()
        self._results = [
            cls._score_or_error(p, root) for p in SourceSelection(target).files()
        ]
        return self

    @property
    def results(self) -> list[dict[str, float | int | str]]:
        """Return the per-file metric dicts."""
        return self._results

    @property
    def rows(self) -> dict[str, dict[str, float]]:
        """Return each parsed file's gated metric values, keyed by path."""
        return {
            str(r["file"]): {k: float(r[k]) for k in Thresholds.names() if k in r}
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
            k: "PASS" if Thresholds.meets(k, v) else "FAIL"
            for k, v in self.summary.items()
        }

    @property
    def fail_count(self) -> int:
        """Return the number of aggregated metrics that fail their threshold."""
        return sum(1 for g in self.grades.values() if g == "FAIL")

    @staticmethod
    def _normalize(path: Path, root: Path) -> str:
        resolved = path.resolve()
        try:
            return resolved.relative_to(root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()

    @classmethod
    def _score_file(cls, path: Path, root: Path) -> dict[str, float | int | str]:
        source = path.read_text(encoding="utf-8")
        return ModuleMetrics(cls._normalize(path, root), source).compute()

    @classmethod
    def _score_or_error(cls, path: Path, root: Path) -> dict[str, float | int | str]:
        try:
            return cls._score_file(path, root)
        except (SyntaxError, UnicodeDecodeError, OSError) as e:
            return {"file": cls._normalize(path, root), "error": str(e)}

    def _aggregate(self) -> dict[str, float]:
        agg: dict[str, list[float]] = {k: [] for k in Thresholds.names()}
        for r in self._results:
            if "error" in r:
                continue
            for k in Thresholds.names():
                if k in r:
                    agg[k].append(float(r[k]))
        summary: dict[str, float] = {}
        for k, values in agg.items():
            if not values:
                continue
            if k in _MAX_AGGREGATED:
                summary[k] = max(values)
            elif k in _MIN_AGGREGATED:
                summary[k] = min(values)
            else:
                summary[k] = round(sum(values) / len(values), 3)
        return summary

    def render_table(self) -> list[str]:
        """Return the aggregate metric table as report lines."""
        summary = self.summary
        grades = self.grades
        lines = [
            f"\n{'Metric':<28} {'Value':>8} {'Target':>10} {'Grade':>6}",
            "-" * 56,
        ]
        for k in Thresholds.names():
            if k not in summary:
                continue
            op, target_val = Thresholds.TABLE[k]
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
                if k == "file" or k not in Thresholds.TABLE:
                    continue
                g = "PASS" if Thresholds.meets(k, float(v)) else "FAIL"
                lines.append(f"    {k:<26} {v:>8} {g}")
        return lines

    def to_json(self) -> str:
        """Return per-file, aggregate, grades, and thresholds as JSON."""
        output = {
            "per_file": self._results,
            "aggregate": self.summary,
            "grades": self.grades,
            "thresholds": {k: Thresholds.describe(k) for k in Thresholds.names()},
        }
        return json.dumps(output, indent=2)
