"""Render a layer scan as text or JSON without judging it."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Self

from oo_ratchet.design.layer_edges import Violation

from .scan import LayerScan


class LayersReport:
    """The view of a scan: violations grouped by layer pair, unassigned modules."""

    _scan: LayerScan

    def __new__(cls, scan: LayerScan) -> Self:
        self = super().__new__(cls)
        self._scan = scan
        return self

    def render(self) -> list[str]:
        """Return the report lines, largest layer pair first."""
        groups: defaultdict[tuple[str, str], list[Violation]] = defaultdict(list)
        for found in self._scan.violations:
            groups[found.source_layer, found.target_layer].append(found)
        total = sum(map(len, groups.values()))
        modules = len(self._scan.modules)
        lines = [f"Layer contract: {modules} modules, {total} violations"]
        for (source, target), rows in sorted(
            groups.items(), key=lambda item: (-len(item[1]), item[0])
        ):
            lines.append(f"{source} -> {target}: {len(rows)}")
            lines.extend(f"  {v.edge}" for v in rows)
        unassigned = self._scan.unassigned
        lines.append(f"Unassigned modules: {len(unassigned)} (each fails --check)")
        lines.extend(f"  {module}" for module in unassigned)
        return lines

    def to_json(self) -> str:
        """Return the scan as a JSON object."""
        return json.dumps(
            {
                "modules": len(self._scan.modules),
                "violations": [
                    {
                        "source": v.edge.source,
                        "target": v.edge.target,
                        "source_layer": v.source_layer,
                        "target_layer": v.target_layer,
                    }
                    for v in self._scan.violations
                ],
                "unassigned": list(self._scan.unassigned),
            },
            indent=2,
        )
