"""The working tree, as the layers gate's edge ports ask about it."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from .packagetrees import PackageTree


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
