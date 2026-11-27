"""The work tree as a ``SourceReader``."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Self

from oo_ratchet.core.domain.scores import Measurement


class SourceTree:
    """Score the tree with a gate's scanner; answer questions about its paths.

    ``scan`` is the gate's scorer: it knows its metrics. This adapter knows the
    repository root, so it keeps every path repo-relative and POSIX.
    """

    _root: Path
    _scan: Callable[[], Measurement]

    def __new__(cls, root: Path, scan: Callable[[], Measurement]) -> Self:
        self = super().__new__(cls)
        self._root = root
        self._scan = scan
        return self

    def measure(self) -> Measurement:
        """Score every file of the gate's selection."""
        return self._scan()

    def exists(self, path: str) -> bool:
        """Return whether the repo-relative ``path`` is on disk."""
        return (self._root / path).exists()

    def key(self, requested: str) -> str:
        """Return the repo-relative POSIX key for any spelling of a path.

        An absolute path, a ``./`` prefix or a redundant segment all name the
        same file; a path outside the repository is returned unchanged.
        """
        resolved = (self._root / requested).resolve()
        try:
            return resolved.relative_to(self._root.resolve()).as_posix()
        except ValueError:
            return requested
