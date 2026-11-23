"""Historical suppression counts across namespace portions and source moves."""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol, Self

from oo_ratchet.source_history import SourceHistory
from oo_ratchet.sources import Sources


class ArchiveRepo(Protocol):
    """The Git operations needed to materialize a historical source selection."""

    @property
    def root(self) -> Path | None: ...

    def archive_paths(self, ref: str, paths: Sequence[str], dest: Path) -> None: ...

    def _git(self, args: list[str]) -> str | None: ...


class NamespaceRescan[T]:
    """Use the same union of real source files for current and base counts."""

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
        self._git = git
        self._scan = scan
        self._rebase = rebase
        return self

    def scan(self, ref: str, source: Sources) -> T | None:
        root = self._git.root
        if root is None:
            raise OSError("namespace rescanning requires a git repository")
        if not all(p.is_relative_to(root) for p in source.roots):
            raise OSError("namespace source is outside the git repository")
        renames = self._renames(ref)
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            self._git.archive_paths(ref, self._paths(ref, source, renames), tree)
            target = SourceHistory.at(source, root, tree, renames)
            if isinstance(target, Path):
                return None
            report = self._scan(target, tree)
            return self._rekey(report, renames)

    def _paths(self, ref: str, source: Sources, renames: dict[str, str]) -> list[str]:
        root = self._git.root
        assert root is not None
        listing = self._git._git(["ls-tree", "-r", "-d", "--name-only", "-z", ref])
        if listing is None:
            raise OSError(f"git ls-tree at {ref} failed")
        patterns = SourceHistory.patterns(source, root, renames)
        paths = [
            path
            for path in listing.split("\0")
            if path and any(Path(path).full_match(pattern) for pattern in patterns)
        ]
        config = (source.project or root) / "pyproject.toml"
        relative = config.relative_to(root).as_posix()
        if self._git._git(["cat-file", "-e", f"{ref}:{relative}"]) is not None:
            paths.append(relative)
        return paths

    def _rekey(self, report: T, renames: dict[str, str]) -> T:
        for new, old in renames.items():
            report = self._rebase(report, old, new)
        return report

    def _renames(self, ref: str) -> dict[str, str]:
        output = self._git._git(["diff", "--name-status", "-M", ref])
        if output is None:
            raise OSError(f"git diff against {ref} failed")
        renames: dict[str, str] = {}
        for line in output.splitlines():
            parts = line.split("\t")
            if parts[0].startswith("R") and len(parts) >= 3:
                renames[parts[2]] = parts[1]
        return renames
