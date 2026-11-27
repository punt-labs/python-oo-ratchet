"""Targets that differ by file: a suffix rule and exact-path caps."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from oo_ratchet.core.domain.metrics import Metric


@dataclass(frozen=True, slots=True)
class PathTargets:
    """Which metrics a file is judged by, when a rule or a cap names it.

    ``suffixes`` replace a metric's target for every path ending in the suffix
    (a gate's entry-point module, for example). ``exact`` replace it for one
    repository-relative path (a configured cap). An exact entry wins.
    """

    suffixes: tuple[tuple[str, tuple[Metric, ...]], ...] = ()
    exact: Mapping[str, tuple[Metric, ...]] = field(default_factory=dict)

    def metrics_for(self, path: str, base: tuple[Metric, ...]) -> tuple[Metric, ...]:
        """Return ``base`` with the replacements that apply to ``path``."""
        replaced = {m.name: m for m in base}
        for suffix, metrics in self.suffixes:
            if path.endswith(suffix):
                replaced.update((m.name, m) for m in metrics)
        replaced.update((m.name, m) for m in self.exact.get(path, ()))
        return tuple(replaced[m.name] for m in base)

    def names(self, path: str) -> bool:
        """Return whether any rule or cap applies to ``path``."""
        return path in self.exact or any(path.endswith(s) for s, _ in self.suffixes)
