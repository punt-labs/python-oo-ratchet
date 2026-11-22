"""Layers ratchet check: no new violating edge, no stale baseline entry.

The baseline may only shrink. ``check`` fails on a violating edge the baseline
does not list and on a baselined edge that no longer violates (run ``--update``
to drop it). Against the baseline committed at the merge base it also fails when
the in-tree baseline holds an edge the base did not, so a PR cannot launder a
violation by hand-editing the file. The baseline file is shared by every package
of a repository; each check reads and compares only the scanned package's rows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Self

from oo_ratchet.coupling.outcome import Outcome
from oo_ratchet.design.layer_edges import Edge

from .base_config import BaseConfig
from .baseline import LayersBaseline
from .gitio import LayersGit
from .scan import LayerScan
from .verdict import LayersVerdict
from .widening import PolicyWidening


class LayersRatchet:
    """Enforce the layers gate against the baseline and the merge base."""

    _config: BaseConfig
    _baseline: LayersBaseline
    _git: LayersGit

    def __new__(cls, root: Path, git: LayersGit) -> Self:
        self = super().__new__(cls)
        self._config = BaseConfig(root, git)
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
        allow_config_change: bool = False,
    ) -> Outcome:
        """Compare the scan with the in-tree baseline and the base baseline.

        ``tripwire`` marks the post-merge ``push:[main]`` run: a base that
        predates the baseline is the one-time adoption merge, not a stale branch.
        ``allow_config_change`` accepts a layer policy that widens ``imports``.
        """
        base = self._git.resolve_base(base_ref)
        if base is None:
            blocked = self._no_base(require_base=require_base)
            return blocked or self._verdict(
                scan, None, "", allow_config_change=allow_config_change
            )
        text = self._git.show_baseline_text(base)
        if text is None:
            blocked = self._absent_base_baseline(tripwire=tripwire)
            return blocked or self._verdict(
                scan, None, base, allow_config_change=allow_config_change
            )
        if not self._baseline.exists:
            return Outcome.failed(
                "FAIL: the base has a layers baseline but the tree has none; "
                "restore it or run --update"
            )
        label = f"{base}:{LayersBaseline.FILENAME}"
        parsed = LayersBaseline.parse(text, label)
        scoped = frozenset(e for e in parsed if e.within(scan.package))
        adopting = not scoped and not self._git.package_at(base, scan.package)
        return self._verdict(
            scan,
            None if adopting else scoped,
            base,
            compare=True,
            allow_config_change=allow_config_change,
        )

    def _verdict(
        self,
        scan: LayerScan,
        base_edges: frozenset[Edge] | None,
        base: str,
        *,
        compare: bool = False,
        allow_config_change: bool,
    ) -> Outcome:
        strict = base_edges is not None
        config = self._config.read(scan, base, strict=strict) if compare else None
        under_base: list[Edge] = []
        widened: list[str] = []
        if config is not None:
            if base_edges is not None:
                under_base = sorted(scan.under(config).edges - base_edges)
            if not allow_config_change:
                widened = PolicyWidening.found(scan.config, config)
        return LayersVerdict(
            scan,
            self._baseline.scoped(scan.package),
            base_edges=base_edges,
            base_config=under_base,
            widened=widened,
            base=base,
        ).outcome()

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
