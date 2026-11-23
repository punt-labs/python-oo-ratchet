"""Recognize top-level package names using every regular-package ancestor."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Self

from .listing import NulListing


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
        return prefix == Path(".") or any(
            file == prefix or prefix in file.parents for file in self._files
        )
