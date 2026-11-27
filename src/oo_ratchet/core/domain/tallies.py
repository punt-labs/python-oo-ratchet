"""A tree's suppression counts and the audit record of a write to them."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Self


@dataclass(frozen=True, slots=True)
class Tally:
    """Counts per category and per file; the gate compares their total.

    ``by_file`` keys are repo-relative paths, or a literal per-file-ignores
    pattern from ``pyproject.toml``.
    """

    by_category: Mapping[str, int]
    by_file: Mapping[str, Mapping[str, int]]

    @property
    def total(self) -> int:
        """Return the count across every category."""
        return sum(self.by_category.values())

    def paths(self) -> frozenset[str]:
        """Return the files that carry at least one count."""
        return frozenset(self.by_file)

    def file_total(self, path: str) -> int:
        """Return the count carried by ``path``, 0 when it carries none."""
        return sum(self.by_file.get(path, {}).values())

    def growth(self, base: Tally) -> list[tuple[str, int, int]]:
        """Return (path, base count, count) for each file above its base, sorted."""
        return [
            (path, then, now)
            for path in sorted(self.paths() | base.paths())
            if (now := self.file_total(path)) > (then := base.file_total(path))
        ]

    def rebased(self, old_prefix: str, new_prefix: str) -> Self:
        """Return a copy with ``by_file`` keys moved onto a new root.

        A tally scanned from a temporary materialization of a git ref and one
        scanned from the work tree name the same files under different roots.
        Only keys rooted under ``old_prefix`` are rewritten; a per-file-ignores
        key is a literal ``pyproject.toml`` pattern, already repo-relative and
        identical on both sides, and passes through unchanged. A rewritten
        key can land on an untouched per-file-ignores key: counts merge on
        collision, never overwrite. ``by_category`` carries over unchanged.
        """
        by_file: dict[str, dict[str, int]] = {}
        for path, counts in self.by_file.items():
            new_key = (
                new_prefix + path.removeprefix(old_prefix)
                if path.startswith(old_prefix)
                else path
            )
            for category, count in counts.items():
                key = {"per_file_ignores": path}.get(category, new_key)
                merged = by_file.setdefault(key, {})
                merged[category] = merged.get(category, 0) + count
        return type(self)(dict(self.by_category), by_file)


@dataclass(frozen=True, slots=True)
class TallyRecord:
    """One audited write: a baseline update, a relaxed file or a rebaseline.

    ``kind`` is ``update``, ``relaxed`` or ``rebaseline``. ``before`` and
    ``after`` are a file's counts for ``relaxed``; ``before`` is the old total
    (``None`` at first adoption) for ``rebaseline``.
    """

    kind: str
    total: int = 0
    by_category: Mapping[str, int] = field(default_factory=dict)
    file: str | None = None
    before: int | None = None
    after: int | None = None
    reason: str | None = None
    source: str | None = None
    commit: str | None = None
