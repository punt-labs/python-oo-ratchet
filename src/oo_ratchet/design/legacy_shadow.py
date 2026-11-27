"""The single-tree merge-base scan, preserving legacy path and symlink rules."""

from __future__ import annotations

import os.path
from pathlib import Path
from typing import Self

from oo_ratchet.core.adapters.shadowtree import ShadowTree

from .shadow_keys import KeyChanges
from .shadow_metrics import ShadowMetrics
from .shadow_report import ShadowReport
from .shadow_scan import ShadowScan


class LegacyShadow:
    """Use measured merge-base debt rather than a mutable baseline file."""

    _report: ShadowReport

    def __new__(cls, source: Path, layers: Path | None, ref: str) -> Self:
        self = super().__new__(cls)
        source = Path(os.path.normpath(source.absolute()))
        git = ShadowTree(source)
        root = git.root_over([], "--shadow-check requires a git repository")
        relative = source.resolve().relative_to(root)
        base = git.fork_point(ref)
        override = layers.resolve() if layers is not None else None
        with git.checkout(base) as tree:
            before = ShadowScan(
                tree / relative, tree, override, package_name=source.name
            )
        after = ShadowScan(source, root, override, package_name=source.name)
        self._report = ShadowReport(
            KeyChanges(before.keys, after.keys),
            ShadowMetrics(before.metrics, after.metrics),
            base,
        )
        return self

    @property
    def report(self) -> ShadowReport:
        """Return the measured, advisory comparison."""
        return self._report
