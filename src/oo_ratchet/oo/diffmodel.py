"""Git diff result value object: the touched-file set with renames.

Split out of ``gitio.py`` (which owns *running* git commands) so the parsed
result owns its own parsing: ``Diff.from_name_status`` is an alternative
constructor (PY-CC-5) for ``git diff --name-status -M`` output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Self


@dataclass(frozen=True, slots=True)
class Diff:
    """Files changed across a commit range, with rename provenance.

    ``renames`` maps a new path to the old path it was renamed from, so a
    renamed file can inherit its predecessor's baseline entry (S8).
    """

    touched: frozenset[str]
    renames: dict[str, str] = field(default_factory=dict)

    def python_files(self) -> frozenset[str]:
        """Return the touched paths that are Python modules."""
        return frozenset(p for p in self.touched if p.endswith(".py"))

    @classmethod
    def from_name_status(cls, out: str) -> Self:
        """Parse ``git diff --name-status -M`` output into a ``Diff``."""
        touched: set[str] = set()
        renames: dict[str, str] = {}
        for line in out.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            status = parts[0]
            if status.startswith(("R", "C")) and len(parts) >= 3:
                old, new = parts[1], parts[2]
                touched.add(new)
                if status.startswith("R"):
                    renames[new] = old
            elif len(parts) >= 2:
                touched.add(parts[1])
        return cls(frozenset(touched), renames)
