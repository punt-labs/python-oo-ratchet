"""When no usable comparison base exists: bootstrap-pass or fail closed."""

from __future__ import annotations

from typing import Self

from oo_ratchet.core.domain.verdicts import Verdict

from .ports import BaselineStore, History

TIP = "origin/main"


class Bases:
    """Decide the verdict when the base cannot be resolved or has no baseline.

    Only genuine first adoption bootstraps. With an in-tree baseline present,
    an unresolvable base means a stale or unfetched main: fail rather than
    trust a hand-editable file.
    """

    _history: History
    _store: BaselineStore

    def __new__(cls, history: History, store: BaselineStore) -> Self:
        self = super().__new__(cls)
        self._history = history
        self._store = store
        return self

    def unresolved(self, *, require_base: bool) -> Verdict:
        """Judge a run whose base ref does not resolve."""
        if require_base:
            return Verdict.refused("base-unresolvable")
        if not self._store.exists():
            return Verdict.ok("first-adoption: no base and no in-tree baseline")
        return Verdict.refused("base-stale")

    def undocumented(self, *, tripwire: bool) -> Verdict:
        """Judge a run whose base commit carries no baseline."""
        if tripwire:
            if not self._store.exists():
                return Verdict.refused("tripwire-no-baseline")
            return Verdict.ok("tripwire: base predates baseline adoption")
        tip = self._history.resolve(TIP)
        if tip is None:
            if self._store.exists():
                return Verdict.refused("tip-unresolvable")
            return Verdict.ok("first-adoption: no base baseline and no tip")
        if self._history.baseline_at(tip) is not None:
            return Verdict.refused("base-predates-baseline")
        return Verdict.ok("first-adoption: no baseline at base or tip")
