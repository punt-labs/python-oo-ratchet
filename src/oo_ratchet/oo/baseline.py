"""Project scorer results into the baseline shape."""

from __future__ import annotations

from .thresholds import Thresholds


class Baseline:
    """The OO baseline's row shape: path to gated metric values."""

    @staticmethod
    def metrics_by_file(
        results: list[dict[str, float | int | str]],
    ) -> dict[str, dict[str, float]]:
        """Project scorer results into the baseline shape, skipping errors."""
        out: dict[str, dict[str, float]] = {}
        for r in results:
            if "error" in r:
                continue
            metrics = {k: float(r[k]) for k in Thresholds.names() if k in r}
            out[str(r["file"])] = metrics
        return out
