"""OO quality scorer and baseline ratchet — merge-base comparison in CI."""

from __future__ import annotations

from .cli import Cli, Options, main
from .compare import FileReview, Review, Row
from .diffmodel import Diff
from .gitio import GitError, GitRepo
from .metrics import ModuleMetrics
from .scorer import Scorer
from .thresholds import Thresholds

__all__ = [
    "Cli",
    "Diff",
    "FileReview",
    "GitError",
    "GitRepo",
    "ModuleMetrics",
    "Options",
    "Review",
    "Row",
    "Scorer",
    "Thresholds",
    "main",
]
