"""The ring data a diagram needs, taken from a layer scan."""

from __future__ import annotations

from collections import Counter
from typing import Self

from .scan import LayerScan


class LayerDiagram:
    """Each module's ring, the edges between rings, and the marked violations.

    A ring is the layer name the config assigns: ``entry``, ``adapters``,
    ``application`` or ``domain`` in the fixed form, the declared name otherwise.
    A module no layer claims reports ``None``; the package root is left out when
    unclaimed. Ring edges count the violating layer edges per pair of rings. A
    domain-purity edge (a domain module importing IO) is marked ``io`` and is not
    counted in the ring edges; every other violation is marked ``layer``.
    """

    _scan: LayerScan

    def __new__(cls, scan: LayerScan) -> Self:
        self = super().__new__(cls)
        self._scan = scan
        return self

    def module_rings(self) -> dict[str, str | None]:
        """Return each module's ring, ``None`` when no layer claims it."""
        config = self._scan.config
        rings = {m: config.layer(m) for m in self._scan.modules}
        return {m: r for m, r in rings.items() if r is not None or "." in m}

    def ring_edges(self) -> list[dict[str, str | int]]:
        """Return the violating layer-edge count per ring pair, sorted."""
        purity = self._scan.io_edges
        counts = Counter(
            (v.source_layer, v.target_layer)
            for v in self._scan.violations
            if v.edge not in purity
        )
        return [
            {"source_ring": source, "target_ring": target, "count": n}
            for (source, target), n in sorted(counts.items())
        ]

    def marked_violations(self) -> list[dict[str, str]]:
        """Return every violation with both rings and its kind (``layer`` or ``io``)."""
        purity = self._scan.io_edges
        return [
            {
                "source": v.edge.source,
                "target": v.edge.target,
                "source_ring": v.source_layer,
                "target_ring": v.target_layer,
                "kind": "io" if v.edge in purity else "layer",
            }
            for v in self._scan.violations
        ]

    def as_json(self) -> dict[str, object]:
        """Return the keys ``layers --json`` adds for drawing."""
        return {
            "module_rings": self.module_rings(),
            "ring_edges": self.ring_edges(),
            "marked_violations": self.marked_violations(),
        }
