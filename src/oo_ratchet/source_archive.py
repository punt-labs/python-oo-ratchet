"""Materialize selected historical namespace portions, never unrelated files."""

from __future__ import annotations

from collections.abc import Set
from pathlib import Path
from typing import TYPE_CHECKING, Self

from .source_history import SourceHistory
from .sources import Sources

if TYPE_CHECKING:
    from oo_ratchet.core.application.ports import ArchiveRepo


class SourceArchive:
    """Resolve historical roots before exporting their tracked contents."""

    _git: ArchiveRepo
    _root: Path

    def __new__(cls, git: ArchiveRepo, root: Path) -> Self:
        self = super().__new__(cls)
        self._git, self._root = git, root
        return self

    def at(
        self, ref: str, source: Sources, renames: dict[str, str], tree: Path
    ) -> Path | Sources:
        """Export the selected portions and resolve their historical layout."""
        self._git.archive_paths(ref, self._paths(ref, source, renames), tree)
        return SourceHistory.at(source, self._root, tree, renames)

    def _paths(self, ref: str, source: Sources, renames: dict[str, str]) -> list[str]:
        listing = self._git._git(["ls-tree", "-r", "-t", "--name-only", "-z", ref])
        if listing is None:
            raise OSError(f"git ls-tree at {ref} failed")
        tracked = listing.split("\0")
        patterns = SourceHistory.patterns(source, self._root, renames)
        selected = {p for p in [".", *tracked] if self._matches(p, patterns)}
        return sorted(selected | self._configs(source).intersection(tracked))

    @staticmethod
    def _matches(path: str, patterns: Set[str]) -> bool:
        return bool(path) and any(Path(path).full_match(p) for p in patterns)

    def _configs(self, source: Sources) -> set[str]:
        return {
            (p / "pyproject.toml").relative_to(self._root).as_posix()
            for p in {self._root, source.project or self._root}
        }
