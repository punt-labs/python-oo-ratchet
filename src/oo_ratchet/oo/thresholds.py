"""Metric thresholds and the direction-aware comparison semantics."""

from __future__ import annotations

import operator
from collections.abc import Callable
from typing import ClassVar


class Thresholds:
    """OO metric thresholds plus the ordering semantics each metric obeys.

    A metric's operator (``>=``, ``<=``, ``==``) defines its absolute target.
    Comparisons rank values by badness, where lower is better: the value for
    ``<=``, its negation for ``>=``, and the distance to the target for ``==``.

    A ceiling metric is bad only above its target, so it is ranked by
    ``max(value, target)``: under the ceiling every value ranks the same, so
    growing a small module is neither a regression nor shrinking it an
    improvement; over the ceiling, smaller is better. Module size is a
    ceiling: comparing it file by file rewarded splitting cohesive code into
    many tiny modules (PL-1685). The two averages, parameters and complexity,
    are ceilings too: deleting a trivial function raises a mean while it stays
    under target, and that is a good move, not a regression (PL-1712).
    """

    TABLE: ClassVar[dict[str, tuple[str, float]]] = {
        "encapsulation_ratio": (">=", 1.0),
        "avg_params": ("<=", 4.0),
        "max_complexity": ("<=", 10),
        "avg_complexity": ("<=", 5.0),
        "module_size": ("<=", 400),
        "init_violations": ("==", 0),
        "public_attr_violations": ("==", 0),
        "future_annotations": ("==", 1),
    }
    CEILINGS: ClassVar[frozenset[str]] = frozenset(
        {"module_size", "avg_params", "avg_complexity"}
    )
    _MEETS: ClassVar[dict[str, Callable[[float, float], bool]]] = {
        ">=": operator.ge,
        "<=": operator.le,
        "==": operator.eq,
    }
    _BADNESS: ClassVar[dict[str, Callable[[float, float], float]]] = {
        ">=": lambda value, _target: -value,
        "<=": lambda value, _target: value,
        "==": lambda value, target: abs(value - target),
    }

    @classmethod
    def names(cls) -> tuple[str, ...]:
        """Return the tracked metric names in table order."""
        return tuple(cls.TABLE)

    @classmethod
    def describe(cls, metric: str) -> str:
        """Return a human-readable ``op target`` label for a metric."""
        op, target = cls.TABLE[metric]
        return f"{op} {target}"

    @classmethod
    def meets(cls, metric: str, value: float) -> bool:
        """Return whether value satisfies the metric's absolute threshold."""
        op, target = cls.TABLE[metric]
        return cls._MEETS[op](value, target)

    @classmethod
    def better_or_equal(cls, metric: str, current: float, baseline: float) -> bool:
        """Return whether current is at least as good as baseline."""
        rank = cls._rank(metric)
        return rank(current) <= rank(baseline)

    @classmethod
    def strictly_better(cls, metric: str, current: float, baseline: float) -> bool:
        """Return whether current is strictly better than baseline."""
        rank = cls._rank(metric)
        return rank(current) < rank(baseline)

    @classmethod
    def _rank(cls, metric: str) -> Callable[[float], float]:
        """Return the metric's badness function; lower is better."""
        op, target = cls.TABLE[metric]
        badness = cls._BADNESS[op]
        # A ceiling ranks every value under its target the same; others have no floor.
        floor = (float("-inf"), target)[metric in cls.CEILINGS]
        return lambda value: badness(max(value, floor), target)
