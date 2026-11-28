"""Scan namespace portions in a merge base and working tree."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from oo_ratchet.core.adapters.shadowtree import ShadowTree
from oo_ratchet.source_history import SourceHistory
from oo_ratchet.source_set import SourceSelection

from .comparison import ShadowMetrics
from .shadow_keys import KeyChanges
from .shadow_report import ShadowReport
from .tree import TreeScan


class NamespaceShadow:
    """Measure a joined namespace on both sides of the merge base."""

    _report: ShadowReport

    def __new__(cls, source: SourceSelection, layers: Path | None, ref: str) -> Self:
        self = super().__new__(cls)
        git = ShadowTree(source.anchor)
        root = git.root_over(
            list(source.roots),
            "namespace shadow roots must be inside one git repository",
        )
        base = git.fork_point(ref)
        renames = git.renames(base)
        override = layers.resolve() if layers is not None else None
        with git.checkout(base) as tree:
            before = TreeScan(
                SourceSelection(
                    SourceHistory(source.target).at_base(root, tree, renames)
                ),
                tree,
                override,
                package_name=source.package_name,
            )
        after = TreeScan(source, root, override, package_name=source.package_name)
        self._report = ShadowReport(
            KeyChanges(before.keys, after.keys),
            ShadowMetrics(
                SourceHistory.metrics(before.metrics, renames), after.metrics
            ),
            base,
        )
        return self

    @property
    def report(self) -> ShadowReport:
        """Return the measured namespace comparison."""
        return self._report
