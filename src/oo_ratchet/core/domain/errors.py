"""Failures a gate must report as a controlled non-zero, never a traceback."""

from __future__ import annotations


class StateError(Exception):
    """A gate's recorded state (baseline, audit log, config) is unreadable."""


class GitError(StateError):
    """A git command a gate depends on failed; a failed diff is never "no changes"."""
