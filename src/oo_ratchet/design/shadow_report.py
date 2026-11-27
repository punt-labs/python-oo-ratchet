"""Ordered shadow verdicts and deterministic, advisory-only reports."""

from __future__ import annotations

import json
from typing import Self

from .comparison import ShadowMetrics
from .shadow_keys import KeyChanges


class ShadowReport:
    """Let design-key multiplicities dominate unweighted OO metric deltas."""

    _keys: KeyChanges
    _metrics: ShadowMetrics
    _base: str

    def __new__(cls, keys: KeyChanges, metrics: ShadowMetrics, base: str) -> Self:
        self = super().__new__(cls)
        self._keys = keys
        self._metrics = metrics
        self._base = base
        return self

    @property
    def verdict(self) -> str:
        """Apply the tier order without scores, netting, or weighted sums."""
        if self._keys.added(0):
            return "would-fail: tier0"
        if self._keys.added(1):
            return "would-fail: tier1"
        if self._keys.removed(1):
            return "good-deed: trade"
        if self._metrics.regressed:
            return "would-fail: tier2"
        if self._metrics.improved:
            return "good-deed"
        return "neutral"

    def to_json(self) -> str:
        """Serialize stable identities, never checkout paths or timestamps."""
        return json.dumps(
            {
                "advisory": True,
                "base": self._base,
                "verdict": self.verdict,
                "tier0": self._keys.mapping(0),
                "tier1": self._keys.mapping(1),
                "tier2": self._metrics.mapping(
                    trade=self.verdict == "good-deed: trade"
                ),
            },
            indent=2,
            sort_keys=True,
        )

    def to_text(self) -> str:
        """Put the verdict first, then design-key changes and OO deltas."""
        lines = [f"{self.verdict} (shadow; advisory)", f"merge-base: {self._base}"]
        for tier in (0, 1):
            lines.extend(self._key_lines(tier))
        lines.append("tier2 deltas:")
        lines.extend(row.render() for row in self._metrics.rows)
        if self.verdict == "good-deed: trade":
            lines.append("tier2 accepted regressions:")
            lines.extend(
                f"  {path} {metric}" for path, metric in self._metrics.regressed
            )
        return "\n".join(lines) + "\n"

    def _key_lines(self, tier: int) -> list[str]:
        changes = self._keys.mapping(tier)
        lines: list[str] = []
        for direction, keys in changes.items():
            lines.append(f"tier{tier} {direction} ({len(keys)}):")
            lines.extend(f"  ({k['rule']}, {k['module']}, {k['symbol']})" for k in keys)
        return lines
