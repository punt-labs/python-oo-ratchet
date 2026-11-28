"""OO quality scorer and baseline ratchet — merge-base comparison in CI."""

from __future__ import annotations

from .cli import main
from .metrics import ModuleMetrics
from .thresholds import OO_METRICS

__all__ = [
    "OO_METRICS",
    "ModuleMetrics",
    "main",
]
