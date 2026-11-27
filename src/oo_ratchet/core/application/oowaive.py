"""The OO gate's scoped bless: the refusal names each metric's value and target."""

from __future__ import annotations

from typing import TYPE_CHECKING

from oo_ratchet.core.domain.scores import Rows

from .waive import RebaselineFiles

if TYPE_CHECKING:
    from .blessbase import BlessBase


class OoRebaselineFiles(RebaselineFiles):
    """Bless named files, explaining a refusal as ``metric=value fails target``."""

    def _partition(
        self, paths: list[str], current: Rows, base: BlessBase
    ) -> tuple[list[str], list[str]]:
        accepted: list[str] = []
        refused: list[str] = []
        for requested in paths:
            path = self._source.key(requested)
            if path not in current:
                refused.append(f"{requested}: not found in scored tree")
                continue
            gated = self._policy.over_cap_and_regressed(current[path], base.row(path))
            if gated:
                refused.append(f"{requested}: {self._why(current[path], gated)}")
            else:
                accepted.append(path)
        return accepted, refused

    def _why(self, entry: dict[str, float], gated: list[str]) -> str:
        return "; ".join(
            f"{m}={entry[m]:g} fails {self._policy.metric(m).describe()} "
            "(over cap and regressed)"
            for m in gated
        )
