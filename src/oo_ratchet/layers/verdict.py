"""The layers gate's verdict: every way a scan can fail the baseline, in one report."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Self

from oo_ratchet.coupling.outcome import Outcome
from oo_ratchet.design.layer_edges import Edge

from .scan import LayerScan


class LayersVerdict:
    """Weigh a scan against the baseline, the base baseline and the base config."""

    _scan: LayerScan
    _recorded: frozenset[Edge]
    _base_edges: frozenset[Edge] | None
    _base_config: list[Edge]
    _base: str

    def __new__(
        cls,
        scan: LayerScan,
        recorded: frozenset[Edge],
        *,
        base_edges: frozenset[Edge] | None,
        base_config: list[Edge],
        base: str,
    ) -> Self:
        self = super().__new__(cls)
        self._scan = scan
        self._recorded = recorded
        self._base_edges = base_edges
        self._base_config = base_config
        self._base = base
        return self

    def outcome(self) -> Outcome:
        """Return a failure naming every finding, or the PASS line."""
        found = {v.edge: str(v) for v in self._scan.violations}
        new = sorted(set(found) - self._recorded)
        sections = (
            ("layer violations not in the baseline:", [found[e] for e in new]),
            (
                "baseline entries that no longer violate (--update):",
                self._edges(self._recorded - set(found)),
            ),
            (
                f"baseline holds edges the base {self._base[:10]} did not:",
                self._edges(self._grown()),
            ),
            (
                "edges that violate under the base config, not in the base baseline:",
                self._edges(e for e in self._base_config if e not in new),
            ),
            ("the layer contract does not cover the package:", self._scan.problems),
        )
        lines = [
            line
            for title, rows in sections
            if rows
            for line in (f"FAIL: {title}", *(f"  {row}" for row in rows))
        ]
        return Outcome(1, tuple(lines)) if lines else self._passed(len(found))

    def _grown(self) -> frozenset[Edge]:
        if self._base_edges is None:
            return frozenset()
        return self._recorded - self._base_edges

    @staticmethod
    def _edges(edges: Iterable[Edge]) -> list[str]:
        return [str(e) for e in sorted(edges)]

    def _passed(self, violations: int) -> Outcome:
        scan = self._scan
        counts = f"{len(scan.modules)} modules scanned"
        counts += f", {len(scan.unassigned)} unassigned"
        return Outcome.passed(
            f"PASS: {counts}, {violations} baselined layer violations, none new/stale"
        )
