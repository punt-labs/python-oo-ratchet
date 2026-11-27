"""The OO gate's metrics: one ``Metric`` per name, with target and direction.

A metric's operator (``>=``, ``<=``, ``==``) defines its absolute target.
``Metric`` ranks values by badness, where lower is better: the value for
``<=``, its negation for ``>=``, and the distance to the target for ``==``.

A ceiling metric is bad only above its target, so it is ranked by
``max(value, target)``: under the ceiling every value ranks the same, so
growing a small module is neither a regression nor shrinking it an
improvement; over the ceiling, smaller is better. Module size is a ceiling:
comparing it file by file rewarded splitting cohesive code into many tiny
modules (PL-1685). The two averages, parameters and complexity, are ceilings
too: deleting a trivial function raises a mean while it stays under target,
and that is a good move, not a regression (PL-1712).
"""

from __future__ import annotations

from oo_ratchet.core.domain.metrics import MetricSet

OO_METRICS = MetricSet.from_table(
    {
        "encapsulation_ratio": (">=", 1.0),
        "avg_params": ("<=", 4.0),
        "max_complexity": ("<=", 10),
        "avg_complexity": ("<=", 5.0),
        "module_size": ("<=", 400),
        "init_violations": ("==", 0),
        "public_attr_violations": ("==", 0),
        "future_annotations": ("==", 1),
    },
    ceilings=("module_size", "avg_params", "avg_complexity"),
)
