"""Repository trees the layers gate asks about: a commit's, and the working tree's."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from .packagetrees import PackageTree


class BaseTree:
    """The files committed at one ref, read once.

    A failing ``git ls-tree`` raises ``GitError`` when the tree is built, so
    nothing here ever reads a failed call as "absent".
    """

    _tree: PackageTree

    def __new__(cls, ref: str, root: Path) -> Self:
        self = super().__new__(cls)
        self._tree = PackageTree.base(ref, root)
        return self

    def package_at(self, name: str) -> bool:
        """Return whether the tree has a top-level package directory ``name``.

        A directory named ``name`` inside another package (``core/utils``) is a
        different import name and does not count.
        """
        return self._tree.package_at(name)

    def path_at(self, path: str) -> bool:
        """Return whether anything exists at repo-relative ``path`` in the tree."""
        return self._tree.path_at(path)


class WorkingTree:
    """The files present in the working tree, tracked or not."""

    _tree: PackageTree

    def __new__(cls, root: Path) -> Self:
        self = super().__new__(cls)
        self._tree = PackageTree.working(root)
        return self

    def has_package(self, name: str) -> bool:
        """Return whether a package directory ``name`` exists in the working tree.

        Tracked files that were deleted but not yet staged do not count; a failing
        git call raises ``GitError`` rather than reading as "absent".
        """
        return self._tree.package_at(name)
