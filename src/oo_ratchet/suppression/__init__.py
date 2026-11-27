"""Count lint/type suppressions in a Python codebase and enforce a ratchet."""

from __future__ import annotations

from .cli import Cli, Options, main
from .patterns import FileSuppressions
from .pyproject import PerFileIgnoresCounter
from .report import SuppressionReport
from .scanner import Scanner

__all__ = [
    "Cli",
    "FileSuppressions",
    "Options",
    "PerFileIgnoresCounter",
    "Scanner",
    "SuppressionReport",
    "main",
]
