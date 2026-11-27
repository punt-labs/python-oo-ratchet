"""The OO gate's scoped bless: the refusal names each metric's value and target."""

from __future__ import annotations

from .waive import RebaselineFiles


class OoRebaselineFiles(RebaselineFiles):
    """Bless named files, explaining a refusal as ``metric=value fails target``."""

    def _why(self, entry: dict[str, float], gated: list[str]) -> str:
        return "; ".join(
            f"{m}={entry[m]:g} fails {self._policy.metric(m).describe()} "
            "(over cap and regressed)"
            for m in gated
        )
