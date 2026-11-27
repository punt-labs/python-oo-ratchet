"""A metric's target and the direction-aware order of its values."""

from __future__ import annotations

import operator
from collections.abc import Callable
from dataclasses import dataclass
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

    def describe(self) -> str:
        """Return the ``op target`` label."""
        return f"{self.op} {self.target}"

    def _rank(self, value: float) -> float:
        floor = self.target if self.ceiling else float("-inf")
        return self.BADNESS[self.op](max(value, floor), self.target)
