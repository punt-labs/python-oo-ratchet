"""Module coupling/cohesion scorer and regression ratchet — merge-base scoped."""

from __future__ import annotations

from .cli import main
from .scorer import CouplingScorer
from .thresholds import CouplingTargets

__all__ = ["CouplingScorer", "CouplingTargets", "main"]
