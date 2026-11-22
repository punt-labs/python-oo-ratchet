"""Scan a merge base and working tree, then report a non-gating ratchet."""

from __future__ import annotations

import os.path
from pathlib import Path
from typing import Self

from oo_ratchet.oo.gitio import GitError, GitRepo

from .shadow_keys import KeyChanges
from .shadow_metrics import ShadowMetrics
from .shadow_report import ShadowReport
from .shadow_scan import ShadowScan
from .shadow_snapshot import ShadowSnapshot


class ShadowCheck:
    """Use measured merge-base debt rather than a mutable baseline file."""

    _report: ShadowReport

    def __new__(cls, source: Path, layers: Path | None, ref: str) -> Self:
        self = super().__new__(cls)
        source = Path(os.path.normpath(source.absolute()))
        git = GitRepo(source)
        root = git.root
        if root is None:
            raise GitError("--shadow-check requires a git repository")
        relative = source.resolve().relative_to(root)
        resolved = git.resolve_ref(ref)
        base = git.merge_base(resolved, "HEAD") if resolved is not None else None
        if base is None:
            raise GitError("--shadow-check ref has no resolvable merge base with HEAD")
        override = layers.resolve() if layers is not None else None
        with ShadowSnapshot(git, base).checkout() as tree:
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
