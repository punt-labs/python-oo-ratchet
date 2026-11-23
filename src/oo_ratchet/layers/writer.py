"""Layers baseline update: adopt a first baseline, then only ever shrink it.

Refuses to run under ``GITHUB_ACTIONS`` unless ``--allow-ci-write`` is passed.
The baseline file is shared by the repository's packages: an update replaces
only the scanned package's rows and keeps every other package's.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Self

from oo_ratchet.coupling.outcome import Outcome
from oo_ratchet.design.layer_edges import Edge

from .audit import LayersAudit
from .baseline import LayersBaseline
from .gitio import LayersGit
from .scan import LayerScan
from .trees import WorkingTree


class LayersWriter:
    """Rewrite the baseline to the current violations, never adding one."""

    _baseline: LayersBaseline
    _audit: LayersAudit
    _git: LayersGit
    _tree: WorkingTree

    def __new__(cls, root: Path, git: LayersGit) -> Self:
        self = super().__new__(cls)
        self._baseline = LayersBaseline(root)
        self._audit = LayersAudit(root)
        self._git = git
        self._tree = WorkingTree(root)
        return self

    def update(
        self,
        scan: LayerScan,
        *,
        allow_ci_write: bool,
        source: str | None,
        config_change: bool = False,
    ) -> Outcome:
        """Write the current violations as the baseline and record the change.

        With no baseline file yet, every current violation is adopted. With one,
        a violation it does not list is refused and nothing is written: the only
        way to loosen the baseline is to fix the code or edit the file by hand,
        and ``check`` rejects a hand edit that grows it past the merge base. If
        the audit entry cannot be written, the previous baseline is put back.
        """
        blocked = self._blocked(scan, allow_ci_write=allow_ci_write)
        if blocked is not None:
            return blocked
        current = frozenset(v.edge for v in scan.violations)
        recorded = self._baseline.scoped(scan.package)
        adopting = not recorded
        retired = self._retired(scan.package)
        before = self._baseline.raw()
        kept = self._baseline.edges - recorded - retired
        self._baseline.save(kept | current)
        try:
            self._audit.append(
                verdict="adopt" if adopting else "pass",
                modules=len(scan.modules),
                violations=len(current),
                added=current if adopting else frozenset(),
                removed=recorded - current,
                commit=self._git.short_head(),
                source=source,
                config_change=config_change,
                retired=retired,
            )
        except OSError:
            self._baseline.restore(before)
            raise
        return Outcome.passed(
            f"Wrote {self._baseline.path}",
            f"  violations: {len(current)} ({len(recorded - current)} removed)",
        )

    def _blocked(self, scan: LayerScan, *, allow_ci_write: bool) -> Outcome | None:
        """Return the refusal that stops an update, or ``None`` when it may write."""
        if os.environ.get("GITHUB_ACTIONS") == "true" and not allow_ci_write:
            return Outcome.failed(
                "FAIL: refusing to write layers baseline under GITHUB_ACTIONS "
                "without --allow-ci-write"
            )
        refusals = {
            "a package the layers do not cover": list(scan.problems),
            "new layer violations": self._added(scan),
        }
        for what, rows in refusals.items():
            if rows:
                return Outcome(
                    1,
                    (f"FAIL: refusing to baseline {what}:", *(f"  {r}" for r in rows)),
                )
        return None

    def _added(self, scan: LayerScan) -> list[str]:
        known = self._baseline.scoped(scan.package)
        if not known:
            return []
        return [str(e) for e in sorted(scan.edges - known)]

    def _retired(self, package: str) -> frozenset[Edge]:
        """Return rows whose package directory no longer exists in the repository."""
        gone = {
            e.source.split(".")[0]
            for e in self._baseline.edges
            if not e.within(package)
        }
        dead = {n for n in gone if n.isidentifier() and not self._tree.has_package(n)}
        return frozenset(
            e for e in self._baseline.edges if e.source.split(".")[0] in dead
        )
