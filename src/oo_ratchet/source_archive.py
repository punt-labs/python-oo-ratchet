"""Materialize selected historical namespace portions, never unrelated files."""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Set
from pathlib import Path
from typing import TYPE_CHECKING, Self

from .source_history import SourceHistory
from .sources import Sources

if TYPE_CHECKING:
    from oo_ratchet.core.application.ports import ArchiveRepo


class SourceArchive[T]:
    """Export the base commit's portions, scan them, and key the result as now."""

    _git: ArchiveRepo
    _scan: Callable[[Path | Sources, Path], T]
    _rebase: Callable[[T, str, str], T]

    def __new__(
        cls,
        git: ArchiveRepo,
        scan: Callable[[Path | Sources, Path], T],
        rebase: Callable[[T, str, str], T],
    ) -> Self:
        self = super().__new__(cls)
        self._git, self._scan, self._rebase = git, scan, rebase
        return self

    def scan(self, ref: str, source: Sources) -> T | None:
        """Scan the namespace portions as they stood at ``ref``."""
        root = self._root(source)
        renames = self._renames(ref)
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            self._git.archive_paths(ref, self._paths(ref, source, renames, root), tree)
            target = SourceHistory.at(source, root, tree, renames)
            if isinstance(target, Path):
                return None
            report = self._scan(target, tree)
            for new, old in renames.items():
                report = self._rebase(report, old, new)
            return report

    def _root(self, source: Sources) -> Path:
        root = self._git.root
        if root is None:
            raise OSError("namespace rescanning requires a git repository")
        if not all(p.is_relative_to(root) for p in source.roots):
            raise OSError("namespace source is outside the git repository")
        return root

    @staticmethod
    def _output(git: ArchiveRepo, args: list[str], failure: str) -> str:
        output = git._git(args)
        if output is None:
            raise OSError(failure)
        return output

    def _renames(self, ref: str) -> dict[str, str]:
        output = self._output(
            self._git,
            ["diff", "--name-status", "-M", ref],
            f"git diff against {ref} failed",
        )
        renames: dict[str, str] = {}
        for line in output.splitlines():
            parts = line.split("\t")
            if parts[0].startswith("R") and len(parts) >= 3:
                renames[parts[2]] = parts[1]
        return renames

    def _paths(
        self, ref: str, source: Sources, renames: dict[str, str], root: Path
    ) -> list[str]:
        listing = self._output(
            self._git,
            ["ls-tree", "-r", "-t", "--name-only", "-z", ref],
            f"git ls-tree at {ref} failed",
        )
        tracked = listing.split("\0")
        patterns = SourceHistory.patterns(source, root, renames)
        selected = {p for p in [".", *tracked] if self._matches(p, patterns)}
        return sorted(selected | self._configs(source, root).intersection(tracked))

    @staticmethod
    def _matches(path: str, patterns: Set[str]) -> bool:
        return bool(path) and any(Path(path).full_match(p) for p in patterns)

    @staticmethod
    def _configs(source: Sources, root: Path) -> set[str]:
        return {
            (p / "pyproject.toml").relative_to(root).as_posix()
            for p in {root, source.project or root}
        }
