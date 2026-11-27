"""OO quality scorer and baseline ratchet — merge-base comparison in CI."""

from __future__ import annotations

from .cli import OoCommand, OoOptions, main
from .metrics import ModuleMetrics
from .scorer import Scorer
from .thresholds import OO_METRICS

__all__ = [
    "OO_METRICS",
    "ModuleMetrics",
    "OoCommand",
    "OoOptions",
    "Scorer",
    "main",
]
