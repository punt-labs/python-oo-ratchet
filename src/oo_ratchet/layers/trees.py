"""Repository trees the layers gate asks about: a commit's, and the working tree's."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from .listing import NulListing


class BaseTree:
    """The files committed at one ref, read once.

    A failing ``git ls-tree`` raises ``GitError`` when the tree is built, so
    nothing here ever reads a failed call as "absent".
    """

    _files: frozenset[str]

    def __new__(cls, ref: str, root: Path) -> Self:
        self = super().__new__(cls)
        listing = NulListing.run(root, ["ls-tree", "-r", "--name-only", "-z", ref])
        self._files = frozenset(listing)
        return self

    def package_at(self, name: str) -> bool:
        """Return whether the tree has a top-level package directory ``name``.

        A directory named ``name`` inside another package (``core/utils``) is a
        different import name and does not count.
        """
        for line in self._files:
            folder = line.removesuffix("__init__.py").rstrip("/")
            head, _, last = folder.rpartition("/")
            if not line.endswith("__init__.py") or last != name:
                continue
            if (f"{head}/__init__.py" if head else "__init__.py") not in self._files:
                return True
        return False

    def path_at(self, path: str) -> bool:
        """Return whether anything exists at repo-relative ``path`` in the tree."""
        prefix = path.rstrip("/") + "/"
        return path == "." or any(
            f == path or f.startswith(prefix) for f in self._files
        )


class WorkingTree:
    """The files present in the working tree, tracked or not."""

    _root: Path

    def __new__(cls, root: Path) -> Self:
        self = super().__new__(cls)
        self._root = root
        return self

    def has_package(self, name: str) -> bool:
        """Return whether a package directory ``name`` exists in the working tree.

        Tracked files that were deleted but not yet staged do not count; a failing
        git call raises ``GitError`` rather than reading as "absent".
        """
        glob = f":(glob)**/{name}/**/*.py"
        args = ["ls-files", "-z", "--cached", "--others", "--exclude-standard", "--"]
        found = NulListing.run(self._root, [*args, glob])
        return any((self._root / line).is_file() for line in found)
