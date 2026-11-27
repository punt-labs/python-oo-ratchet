"""Check a base commit out beside the work tree, read-only, and clean it up."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Self

from oo_ratchet.core.domain.errors import GitError

from .gitrepo import GitRepo

if TYPE_CHECKING:
    from collections.abc import Iterator

_CHECKOUT_TIMEOUT = 300


class ShadowTree:
    """Resolve a base commit and check it out as an isolated detached tree."""

    _git: GitRepo

    def __new__(cls, start: Path) -> Self:
        self = super().__new__(cls)
        self._git = GitRepo.stateless(start)
        return self

    def root_over(self, paths: list[Path], message: str) -> Path:
        """Return the repository root, or raise ``GitError(message)``."""
        root = self._git.root
        if root is None or not all(p.is_relative_to(root) for p in paths):
            raise GitError(message)
        return root

    def fork_point(self, ref: str) -> str:
        """Return the commit where ``ref`` diverges from HEAD."""
        commit = self._git.resolve(ref)
        out = self._git.run(["merge-base", commit, "HEAD"]) if commit else None
        if not out or not out.strip():
            raise GitError("--shadow-check ref has no resolvable merge base with HEAD")
        return out.strip()

    def renames(self, base: str) -> dict[str, str]:
        """Return the paths renamed since ``base``, as new path to old path."""
        return self._git.changes_since(base).renames

    @contextmanager
    def checkout(self, base: str) -> Iterator[Path]:
        """Yield the detached base tree without touching the caller's checkout."""
        root = self._git.root
        if root is None:
            raise GitError("shadow checking requires a git repository")
        temporary = TemporaryDirectory(prefix="oo-shadow-")
        tree = Path(temporary.name) / root.name
        try:
            with temporary:
                args = ["worktree", "add", "--quiet", "--detach", str(tree), base]
                if self._git.run(args, _CHECKOUT_TIMEOUT) is None:
                    raise GitError("cannot check out the shadow merge base")
                yield tree
        finally:
            self._unregister(tree)

    def _unregister(self, tree: Path) -> None:
        listing = self._git.run(["worktree", "list", "--porcelain", "-z"])
        if listing is None:
            raise GitError("cannot inspect shadow merge-base worktrees")
        record = next(
            (
                r
                for r in listing.split("\0\0")
                if r.split("\0")[0] == f"worktree {tree}"
            ),
            "",
        )
        if not record:
            return
        locked = any(
            f == "locked" or f.startswith("locked ") for f in record.split("\0")
        )
        if locked and self._git.run(["worktree", "unlock", str(tree)]) is None:
            raise GitError("cannot unlock the shadow merge-base worktree")
        if self._git.run(["worktree", "remove", str(tree)]) is None:
            raise GitError("cannot unregister the shadow merge-base worktree")
