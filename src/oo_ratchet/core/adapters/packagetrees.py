"""Repository trees: the packages a commit holds, and the working tree's."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Self

from .nullisting import NulListing


class PackageTree:
    """Classify committed and live paths with the same package ancestry rules."""

    _files: frozenset[Path]

    def __new__(cls, paths: Iterable[str]) -> Self:
        self = super().__new__(cls)
        self._files = frozenset(Path(p) for p in paths)
        return self

    @classmethod
    def base(cls, ref: str, root: Path) -> Self:
        """Read the committed files, preserving unusual path bytes."""
        return cls(NulListing.run(root, ["ls-tree", "-r", "--name-only", "-z", ref]))

    @classmethod
    def working(cls, root: Path) -> Self:
        """Read tracked and untracked files that still exist."""
        args = ["ls-files", "-z", "--cached", "--others", "--exclude-standard"]
        return cls(p for p in NulListing.run(root, args) if (root / p).is_file())

    def package_at(self, name: str) -> bool:
        """Recognize regular or namespace roots, never nested namesakes."""
        return any(
            p.name == name and not self._nested(p)
            for file in self._files
            if file.suffix == ".py"
            for p in file.parents
        )

    def _nested(self, path: Path) -> bool:
        return any(p / "__init__.py" in self._files for p in path.parents)

    def path_at(self, path: str) -> bool:
        """Return whether a file or directory exists in this snapshot."""
        prefix = Path(path)
        return prefix == Path() or any(
            file == prefix or prefix in file.parents for file in self._files
        )


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
