"""A metric's target and the direction-aware order of its values."""

from __future__ import annotations

import operator
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from operator import attrgetter
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class Metric:
    """One gated metric: an absolute target and which way is better.

    ``op`` is ``>=``, ``<=`` or ``==``. Values are ranked by badness, lower
    being better: the value for ``<=``, its negation for ``>=``, the distance
    to the target for ``==``. A ceiling metric is bad only above its target, so
    every value under the target ranks the same.
    """

    name: str
    op: str
    target: float
    ceiling: bool = False

    MEETS: ClassVar[dict[str, Callable[[float, float], bool]]] = {
        ">=": operator.ge,
        "<=": operator.le,
        "==": operator.eq,
    }
    BADNESS: ClassVar[dict[str, Callable[[float, float], float]]] = {
        ">=": lambda value, _target: -value,
        "<=": lambda value, _target: value,
        "==": lambda value, target: abs(value - target),
    }

    def meets(self, value: float) -> bool:
        """Return whether ``value`` satisfies the absolute target."""
        return self.MEETS[self.op](value, self.target)

    def better_or_equal(self, current: float, baseline: float) -> bool:
        """Return whether ``current`` is at least as good as ``baseline``."""
        return self._rank(current) <= self._rank(baseline)

    def strictly_better(self, current: float, baseline: float) -> bool:
        """Return whether ``current`` is strictly better than ``baseline``."""
        return self._rank(current) < self._rank(baseline)

    def classify(self, current: float, base: float | None, *, waived: bool) -> str:
        """Return the status of ``current`` against ``base``.

        A metric missing from the base row is judged by its target: a
        hand-edited row cannot hide a regression or earn must-improve credit.
        """
        if base is None:
            return ("REGRESSED", "PASS")[self.meets(current)]
        verdicts = {
            (True, True): "IMPROVED",
            (False, True): "PASS",
            (False, False): ("REGRESSED", "RELAXED")[waived],
        }
        return verdicts[
            self.strictly_better(current, base), self.better_or_equal(current, base)
        ]

    def describe(self) -> str:
        """Return the ``op target`` label."""
        return f"{self.op} {self.target}"

    def _rank(self, value: float) -> float:
        floor = self.target if self.ceiling else float("-inf")
        return self.BADNESS[self.op](max(value, floor), self.target)


@dataclass(frozen=True, slots=True)
class MetricSet:
    """The metrics one gate tracks, in table order."""

    items: tuple[Metric, ...]

    @classmethod
    def from_table(
        cls,
        table: Mapping[str, tuple[str, float]],
        ceilings: Collection[str] = (),
    ) -> MetricSet:
        """Build the set from an ``{name: (op, target)}`` table."""
        return cls(
            tuple(
                Metric(name, op, target, name in ceilings)
                for name, (op, target) in table.items()
            )
        )

    @property
    def names(self) -> tuple[str, ...]:
        """Return the metric names in table order."""
        return tuple(m.name for m in self.items)

    @property
    def ceilings(self) -> tuple[str, ...]:
        """Return the names of the ceiling metrics."""
        return tuple(m.name for m in filter(attrgetter("ceiling"), self.items))

    def metric(self, name: str) -> Metric:
        """Return the named metric."""
        return {m.name: m for m in self.items}[name]

    def __contains__(self, name: object) -> bool:
        return name in self.names
