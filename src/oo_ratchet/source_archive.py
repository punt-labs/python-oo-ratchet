"""Materialize selected historical namespace portions, never unrelated files."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Self

from .source_history import SourceHistory
from .sources import Sources

if TYPE_CHECKING:
    from .source_rescan import ArchiveRepo


class SourceArchive:
    """Resolve historical roots before exporting their tracked contents."""

    _git: ArchiveRepo
    _root: Path

    def __new__(cls, git: ArchiveRepo, root: Path) -> Self:
        self = super().__new__(cls)
        self._git = git
        self._root = root
        return self

    def at(
        self, ref: str, source: Sources, renames: dict[str, str], tree: Path
    ) -> Path | Sources:
        """Export the selected portions and resolve their historical layout."""
        self._git.archive_paths(ref, self._paths(ref, source, renames), tree)
        return SourceHistory.at(source, self._root, tree, renames)

    def _paths(self, ref: str, source: Sources, renames: dict[str, str]) -> list[str]:
        listing = self._git._git(["ls-tree", "-r", "-d", "--name-only", "-z", ref])
        if listing is None:
            raise OSError(f"git ls-tree at {ref} failed")
        patterns = SourceHistory.patterns(source, self._root, renames)
        paths = [
            path
            for path in [".", *listing.split("\0")]
            if path and any(Path(path).full_match(pattern) for pattern in patterns)
        ]
        config = (source.project or self._root) / "pyproject.toml"
        relative = config.relative_to(self._root).as_posix()
        if self._git._git(["cat-file", "-e", f"{ref}:{relative}"]) is not None:
            paths.append(relative)
        return paths
