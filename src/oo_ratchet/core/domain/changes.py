"""The files a change touched, with renames carried as data."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Self


@dataclass(frozen=True, slots=True)
class Diff:
    """Files changed from a base to the work tree.

    ``renames`` maps a new path to the old path it came from, so a renamed file
    inherits its predecessor's baseline row.
    """

    touched: frozenset[str] = frozenset()
    renames: dict[str, str] = field(default_factory=dict)

    def python_files(self) -> frozenset[str]:
        """Return the touched paths that are Python modules."""
        return frozenset(p for p in self.touched if p.endswith(".py"))

    @classmethod
    def from_name_status(cls, out: str) -> Self:
        """Parse ``git diff --name-status -M`` output."""
        touched: set[str] = set()
        renames: dict[str, str] = {}
        for line in out.splitlines():
            parts = line.split("\t")
            if not line.strip() or len(parts) < 2:
                continue
            status = parts[0]
            if status.startswith(("R", "C")) and len(parts) >= 3:
                touched.add(parts[2])
                if status.startswith("R"):
                    renames[parts[2]] = parts[1]
            else:
                touched.add(parts[1])
        return cls(frozenset(touched), renames)
