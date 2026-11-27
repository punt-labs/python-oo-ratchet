"""OO quality scorer and baseline ratchet — merge-base comparison in CI."""

from __future__ import annotations

from .cli import main
from .metrics import ModuleMetrics
from .scorer import Scorer
from .thresholds import Thresholds

__all__ = [
    "ModuleMetrics",
    "Scorer",
    "Thresholds",
    "main",
]
