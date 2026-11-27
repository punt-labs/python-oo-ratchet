"""When no usable comparison base exists: bootstrap-pass or fail closed."""

from __future__ import annotations

from collections.abc import Callable
from typing import Self

from oo_ratchet.core.domain.verdicts import Verdict

TIP = "origin/main"


class Bases:
    """Decide the verdict when the base cannot be resolved or has no baseline.

    Only genuine first adoption bootstraps. With an in-tree baseline present,
    an unresolvable base means a stale or unfetched main: fail rather than
    trust a hand-editable file.

    The gate supplies three questions: which commit a ref names, whether the
    gate's recorded state exists at a commit, and whether an in-tree baseline
    exists.
    """

    _resolve: Callable[[str | None], str | None]
    _adopted_at: Callable[[str], bool]
    _has_baseline: Callable[[], bool]

    def __new__(
        cls,
        resolve: Callable[[str | None], str | None],
        adopted_at: Callable[[str], bool],
        has_baseline: Callable[[], bool],
    ) -> Self:
        self = super().__new__(cls)
        self._resolve = resolve
        self._adopted_at = adopted_at
        self._has_baseline = has_baseline
        return self

    def unresolved(self, *, require_base: bool) -> Verdict:
        """Judge a run whose base ref does not resolve."""
        if require_base:
            return Verdict.refused("base-unresolvable")
        if not self._has_baseline():
            return Verdict.ok("first-adoption: no base and no in-tree baseline")
        return Verdict.refused("base-stale")

    def undocumented(self, *, tripwire: bool) -> Verdict:
        """Judge a run whose base commit carries no baseline."""
        if tripwire:
            if not self._has_baseline():
                return Verdict.refused("tripwire-no-baseline")
            return Verdict.ok("tripwire: base predates baseline adoption")
        tip = self._resolve(TIP)
        if tip is None:
            if self._has_baseline():
                return Verdict.refused("tip-unresolvable")
            return Verdict.ok("first-adoption: no base baseline and no tip")
        if self._adopted_at(tip):
            return Verdict.refused("base-predates-baseline")
        return Verdict.ok("first-adoption: no baseline at base or tip")
