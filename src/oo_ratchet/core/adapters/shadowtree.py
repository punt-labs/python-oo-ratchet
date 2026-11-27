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

CHECKOUT_TIMEOUT = 300


class ShadowTree:
    """Check out an isolated detached tree and unregister it afterward."""

    _git: GitRepo
    _base: str

    def __new__(cls, git: GitRepo, base: str) -> Self:
        self = super().__new__(cls)
        self._git = git
        self._base = base
        return self

    @contextmanager
    def checkout(self) -> Iterator[Path]:
        """Yield the detached base tree without touching the caller's checkout."""
        root = self._git.root
        if root is None:
            raise GitError("shadow checking requires a git repository")
        temporary = TemporaryDirectory(prefix="oo-shadow-")
        tree = Path(temporary.name) / root.name
        try:
            with temporary:
                args = ["worktree", "add", "--quiet", "--detach", str(tree), self._base]
                if self._git.run(args, CHECKOUT_TIMEOUT) is None:
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
