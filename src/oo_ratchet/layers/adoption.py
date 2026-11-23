"""Decide whether the scanned package is new in this change."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from oo_ratchet.design.layer_edges import Edge

from .scan import LayerScan
from .trees import BaseTree


class Adoption:
    """A package is new only if the base shows no trace of it.

    Traces are baseline rows for its name, a top-level package directory of
    that name anywhere in the base tree, and anything at the scanned
    directory's real path (a symlink or a package at the repository root).
    Anything found means the package is existing and is compared with the base.
    """

    _root: Path

    def __new__(cls, root: Path) -> Self:
        self = super().__new__(cls)
        self._root = root
        return self

    def is_new(self, scan: LayerScan, base: str, rows: frozenset[Edge]) -> bool:
        """Return whether ``scan``'s package did not exist at ``base``."""
        if rows:
            return False
        tree = BaseTree(base, self._root)
        real = scan.src.resolve().relative_to(self._root.resolve())
        return not (tree.package_at(scan.package) or tree.path_at(real.as_posix()))
