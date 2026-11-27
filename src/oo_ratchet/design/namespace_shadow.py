"""Scan namespace portions in a merge base and working tree."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Self

from oo_ratchet.core.adapters.gitrepo import GitRepo
from oo_ratchet.core.adapters.shadowtree import ShadowTree
from oo_ratchet.core.domain.errors import GitError

from .shadow_keys import KeyChanges
from .shadow_metrics import ShadowMetrics
from .shadow_report import ShadowReport
from .shadow_scan import ShadowScan

if TYPE_CHECKING:
    from oo_ratchet.source_set import SourceSet


class NamespaceShadow:
    """Measure a joined namespace on both sides of the merge base."""

    _report: ShadowReport

    def __new__(cls, source: SourceSet, layers: Path | None, ref: str) -> Self:
        self = super().__new__(cls)
        git = GitRepo.stateless(source.anchor)
        root = git.root
        if root is None or not all(p.is_relative_to(root) for p in source.roots):
            raise GitError("namespace shadow roots must be inside one git repository")
        base = git.fork_point(ref)
        if base is None:
            raise GitError("--shadow-check ref has no resolvable merge base with HEAD")
        renames = git.changes_since(base).renames
        override = layers.resolve() if layers is not None else None
        with ShadowTree(git, base).checkout() as tree:
            before = ShadowScan(
                source.at_base(root, tree, renames),
                tree,
                override,
                package_name=source.package_name,
            )
        after = ShadowScan(source, root, override, package_name=source.package_name)
        self._report = ShadowReport(
            KeyChanges(before.keys, after.keys),
            ShadowMetrics(source.remap_metrics(before.metrics, renames), after.metrics),
            base,
        )
        return self

    @property
    def report(self) -> ShadowReport:
        """Return the measured namespace comparison."""
        return self._report
