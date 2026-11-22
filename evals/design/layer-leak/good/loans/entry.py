"""Library-loan design evaluation fixture."""

from __future__ import annotations

from .adapters.store import FeeStore
from .application import quote as calculate


def quote(days: int) -> int:
    return calculate(days, FeeStore())
