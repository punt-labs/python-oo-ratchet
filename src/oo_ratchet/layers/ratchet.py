"""Layers ratchet check: no new violating edge, no stale baseline entry.

The baseline may only shrink. ``check`` fails on a violating edge the baseline
does not list and on a baselined edge that no longer violates (run ``--update``
to drop it). Against the baseline committed at the merge base it also fails when
the in-tree baseline holds an edge the base did not, so a PR cannot launder a
violation by hand-editing the file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Self

from oo_ratchet.coupling.outcome import Outcome
from oo_ratchet.design.layer_edges import Edge
from oo_ratchet.design.layer_table import LayerTable

from .baseline import LayersBaseline
from .gitio import LayersGit
from .scan import LayerScan
from .verdict import LayersVerdict


class LayersRatchet:
    """Enforce the layers gate against the baseline and the merge base."""

    _baseline: LayersBaseline
    _git: LayersGit

    def __new__(cls, root: Path, git: LayersGit) -> Self:
        self = super().__new__(cls)
        self._baseline = LayersBaseline(root)
        self._git = git
        return self

    def check(
        self,
        scan: LayerScan,
        *,
        base_ref: str | None,
        require_base: bool,
        tripwire: bool = False,
    ) -> Outcome:
        """Compare the scan with the in-tree baseline and the base baseline.

        ``tripwire`` marks the post-merge ``push:[main]`` run: a base that
        predates the baseline is the one-time adoption merge, not a stale branch.
        """
        base = self._git.resolve_base(base_ref)
        if base is None:
            blocked = self._no_base(require_base=require_base)
            return blocked or self._verdict(scan, None, "")
        text = self._git.show_baseline_text(base)
        if text is None:
            blocked = self._absent_base_baseline(tripwire=tripwire)
            return blocked or self._verdict(scan, None, base)
        label = f"{base}:{LayersBaseline.FILENAME}"
        return self._verdict(scan, LayersBaseline.parse(text, label), base)

    def _verdict(
        self, scan: LayerScan, base_edges: frozenset[Edge] | None, base: str
    ) -> Outcome:
        return LayersVerdict(
            scan,
            self._baseline.edges,
            base_edges=base_edges,
            base_config=self._under_base(scan, base, base_edges),
            base=base,
        ).outcome()

    def _under_base(
        self, scan: LayerScan, base: str, base_edges: frozenset[Edge] | None
    ) -> list[Edge]:
        """Return edges that break the base config's rules and the base baseline."""
        text = self._git.show_pyproject_text(base) if base_edges is not None else None
        config = LayerTable.from_text(text, f"{base}:pyproject.toml") if text else None
        if config is None or base_edges is None:
            return []
        return sorted(scan.under(config).edges - base_edges)

    def _no_base(self, *, require_base: bool) -> Outcome | None:
        """Fail closed when no base resolves; ``None`` allows a first adoption."""
        if require_base:
            return Outcome.failed(
                "FAIL: base ref unresolvable and --require-base is set"
            )
        if self._baseline.exists:
            return Outcome.failed(
                "FAIL: cannot resolve merge-base (origin/main unfetched or stale) "
                "with an in-tree baseline present; fetch origin/main or pass --base-ref"
            )
        return None

    def _absent_base_baseline(self, *, tripwire: bool) -> Outcome | None:
        """Decide when the base commit has no baseline; ``None`` is adoption."""
        if tripwire:
            if self._baseline.exists:
                return None
            return Outcome.failed(
                "FAIL: --tripwire with no baseline on main; only the "
                "adoption commit that adds the baseline may bootstrap"
            )
        tip = self._git.resolve_ref("origin/main")
        if tip is None:
            if self._baseline.exists:
                return Outcome.failed(
                    "FAIL: base has no baseline and origin/main is unresolvable "
                    "with an in-tree baseline present; fetch origin/main"
                )
            return None
        if self._git.show_baseline_text(tip) is not None:
            return Outcome.failed(
                "FAIL: base commit predates baseline adoption; rebase onto current main"
            )
        return None
