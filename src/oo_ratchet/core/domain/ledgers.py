"""The ceiling ledger: audited, justified per-file count ceilings."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Self


@dataclass(frozen=True, slots=True)
class Ceiling:
    """The count one file may carry, with the reason and when it was set."""

    file: str
    ceiling: int
    justify: str
    added_at: str


@dataclass(frozen=True, slots=True)
class Ledger:
    """Ceilings by file.

    A ceiling waives only the change that adds it. Once the entry reaches the
    comparison base, the base's ledger carries the identical entry and it is
    retired: it covers nothing in any later comparison, so a cleanup that
    lowers the file's count is a real floor.
    """

    entries: Mapping[str, Ceiling] = field(default_factory=dict)

    def ceiling(self, path: str) -> int | None:
        """Return the ceiling recorded for ``path``, ``None`` if unwaived."""
        entry = self.entries.get(path)
        return None if entry is None else entry.ceiling

    def surviving(self, base: Self | None) -> Self:
        """Return the entries the base ledger does not already carry unchanged."""
        merged = base.entries if base is not None else {}
        return type(self)({f: e for f, e in self.entries.items() if merged.get(f) != e})

    def ordered(self) -> tuple[Ceiling, ...]:
        """Return the entries sorted by file."""
        return tuple(sorted(self.entries.values(), key=lambda e: e.file))
