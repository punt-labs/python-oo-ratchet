"""Reconcile: sweep the whole tree, adding improvements and pruning deletions."""

from __future__ import annotations

from oo_ratchet.core.domain.verdicts import Verdict

from .operation import Operation
from .update import PlanApplier, UpdatePlan


class Reconcile(Operation):
    """Write every scored file's row and drop the rows of deleted files.

    The merge-base diff supplies the rename map, so a renamed module is
    compared against its predecessor's row and the old key is not pruned as a
    false deletion. Without a base there is no rename provenance: a repository
    that has a baseline refuses, and only first adoption bootstraps the tree.
    """

    def run(self, *, source: str | None) -> Verdict:
        """Sweep the tree; a regression is refused, as in an update."""
        measured = self._source.measure()
        current = measured.metrics()
        base = self._history.resolve(None)
        if base is None:
            if self._store.exists():
                return Verdict.refused("reconcile-no-base")
            renames: dict[str, str] = {}
        else:
            renames = self._history.changes_since(base).renames
        present = current.keys() | measured.parse_errors
        kept = present | {old for new, old in renames.items() if new in present}
        stale = {path for path in self._store.rows() if path not in kept}
        plan = UpdatePlan(
            current,
            frozenset(current) | stale,
            renames,
            parse_errors=measured.parse_errors,
        )
        return PlanApplier(self._policy, self._ports).apply(plan, source)
