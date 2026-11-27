"""What changed between two sets of baseline rows."""

from __future__ import annotations

from typing import Self

from oo_ratchet.core.domain.scores import Rows

from .policy import GatePolicy

Deltas = dict[str, dict[str, list[float]]]


class RowChanges:
    """The metrics that differ between the recorded rows and the current ones.

    A metric the old row lacks counts from ``0.0``. A file with an old row is
    ``lost`` when any changed metric is worse, else ``gained``.
    """

    _deltas: Deltas
    _lost: frozenset[str]
    _gained: frozenset[str]

    def __new__(cls, policy: GatePolicy, old: Rows, new: Rows) -> Self:
        self = super().__new__(cls)
        self._deltas = {}
        for path, entry in new.items():
            diff = cls._diff(old.get(path, {}), entry)
            if diff:
                self._deltas[path] = diff
        tracked = self._deltas.keys() & old.keys()
        self._lost = frozenset(
            p for p in tracked if cls._loosens(policy, self._deltas[p])
        )
        self._gained = frozenset(tracked - self._lost)
        return self

    @property
    def deltas(self) -> Deltas:
        """Return ``{path: {metric: [old, new]}}`` for every changed file."""
        return self._deltas

    @property
    def gained(self) -> int:
        """Return how many files with an old row changed for the better."""
        return len(self._gained)

    @property
    def lost(self) -> int:
        """Return how many files with an old row changed for the worse."""
        return len(self._lost)

    @staticmethod
    def _diff(old: dict[str, float], entry: dict[str, float]) -> dict[str, list[float]]:
        return {m: [old.get(m, 0.0), v] for m, v in entry.items() if old.get(m) != v}

    @staticmethod
    def _loosens(policy: GatePolicy, diff: dict[str, list[float]]) -> bool:
        return any(
            not policy.metric(m).better_or_equal(new, old)
            for m, (old, new) in diff.items()
        )
