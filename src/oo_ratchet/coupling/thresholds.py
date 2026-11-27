"""The coupling gate's metrics and the targets each file is judged by."""

from __future__ import annotations

from typing import Self

from oo_ratchet.core.domain.metrics import Metric, MetricSet

COUPLING_METRICS = MetricSet.from_table(
    {
        "efferent_coupling": ("<=", 10),
        "public_names": ("<=", 15),
        "circular_imports": ("==", 0),
        "max_lcom": ("<=", 0.8),
        "avg_lcom": ("<=", 0.5),
    }
)

# ``__main__.py`` legitimately wires many modules and exposes many command
# names, so it gets relaxed targets; the direction is the strict table's.
MAIN_METRICS = MetricSet(
    (
        Metric("public_names", "<=", 100),
        Metric("efferent_coupling", "<=", 15),
    )
)

# Metrics whose aggregate is the worst (max) across files; the rest average.
MAX_AGGREGATED = frozenset(
    {"efferent_coupling", "public_names", "circular_imports", "max_lcom"}
)


class CouplingTargets:
    """The target each file is judged against, under its configured caps.

    ``caps`` (exact repo-relative path -> metric -> cap, from
    ``CouplingConfig``) override the target for the named files only; a cap on
    an ``==`` metric is a ceiling. ``__main__.py`` gets the relaxed targets
    while every other file keeps the strict table.
    """

    _caps: dict[str, dict[str, float]]

    def __new__(cls, caps: dict[str, dict[str, float]] | None = None) -> Self:
        self = super().__new__(cls)
        self._caps = caps or {}
        return self

    def capped(self) -> dict[str, tuple[Metric, ...]]:
        """Return each configured path's caps as metrics."""
        return {
            path: tuple(self._capped(name, cap) for name, cap in caps.items())
            for path, caps in self._caps.items()
        }

    def metric(self, name: str, filepath: str = "") -> Metric:
        """Return the metric as ``filepath`` is judged by it."""
        strict = COUPLING_METRICS.metric(name)
        capped = self._caps.get(filepath, {})
        if name in capped:
            return self._capped(name, capped[name])
        if filepath.endswith("__main__.py") and name in MAIN_METRICS:
            return MAIN_METRICS.metric(name)
        return strict

    @staticmethod
    def _capped(name: str, cap: float) -> Metric:
        op = COUPLING_METRICS.metric(name).op
        return Metric(name, "<=" if op == "==" else op, cap)
