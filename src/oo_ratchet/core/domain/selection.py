"""Which source files a gate scans: portions of one import namespace."""

from __future__ import annotations

import keyword
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceSelection:
    """The namespace and repo-relative roots a scan covers, as plain strings."""

    namespace: str
    roots: tuple[str, ...]
    project: str | None = None

    def __post_init__(self) -> None:
        if not self.namespace.isidentifier() or keyword.iskeyword(self.namespace):
            raise ValueError("namespace must be a top-level Python identifier")
        if not self.roots:
            raise ValueError("a selection needs at least one root")

    def covers(self, path: str) -> bool:
        """Return whether ``path`` lies under one of the roots."""
        return any(
            path == r or path.startswith(r.rstrip("/") + "/") for r in self.roots
        )
