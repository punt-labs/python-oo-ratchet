"""The modules a plain package had at the merge base, from its committed tree."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Self

from oo_ratchet.layers.scan import LayersScanError
from oo_ratchet.source_set import Source, SourceSet

from .nullisting import NulListing


class BaseModules:
    """Name the modules a package had at a ref, read from ``git ls-tree``.

    Tracked ``.py`` files are listed whatever ``export-ignore`` says, and no
    scan or validation runs on them, so a base that held only an initializer,
    or no initializer at all, is fine. Paths become names by the working
    tree's own rule (``SourceSet.parts_to_key``). A package with no tracked
    Python at its current directory is looked up by import name among the
    top-level packages: one match is the relocated package, several are
    refused. A namespace selection is not reconstructed: every current module
    counts as present, which is stricter, never looser.
    """

    _root: Path
    _src: Source

    def __new__(cls, root: Path, src: Source) -> Self:
        self = super().__new__(cls)
        self._root = root
        self._src = src
        return self

    def shared(self, modules: Iterable[str], base: str, package: str) -> list[str]:
        """Return the ``modules`` that also existed at ``base``."""
        if SourceSet(self._src).namespace is not None:
            return list(modules)
        files = self._tracked_python(base)
        known = self._names(files, self._prefix(files, package), package)
        return [m for m in modules if m in known]

    def _tracked_python(self, base: str) -> list[PurePosixPath]:
        raw = NulListing.run(self._root, ["ls-tree", "-r", "--name-only", "-z", base])
        return [PurePosixPath(p) for p in raw if p.endswith(".py")]

    @staticmethod
    def _names(
        files: list[PurePosixPath], prefix: PurePosixPath | None, package: str
    ) -> set[str]:
        """Name each file under ``prefix`` by the working tree's own rule."""
        if prefix is None:
            return set()
        parts = (
            f.relative_to(prefix).with_suffix("").parts
            for f in files
            if f.is_relative_to(prefix)
        )
        keys = map(SourceSet.parts_to_key, parts)
        return {BaseModules._name(key, package) for key in keys}

    @staticmethod
    def _name(key: str, package: str) -> str:
        return package if key == "__init__" else f"{package}.{key}"

    def _prefix(self, files: list[PurePosixPath], package: str) -> PurePosixPath | None:
        here = PurePosixPath(
            SourceSet.path(self._src).resolve().relative_to(self._root.resolve())
        )
        if any(f.is_relative_to(here) for f in files):
            return here
        found = self._top_level(files, package)
        self._refuse_several(found, package)
        return found[0] if found else None

    @staticmethod
    def _refuse_several(found: list[PurePosixPath], package: str) -> None:
        if len(found) > 1:
            where = ", ".join(sorted(str(p) for p in found))
            msg = (
                f"cannot tell where package {package!r} was at the base: "
                f"more than one directory holds it ({where})"
            )
            raise LayersScanError(msg)

    @staticmethod
    def _top_level(files: list[PurePosixPath], package: str) -> list[PurePosixPath]:
        """Return the directories named ``package`` that no regular package holds."""
        inits = BaseModules._initializers(files)
        return [d for d in inits if d.name == package and inits.isdisjoint(d.parents)]

    @staticmethod
    def _initializers(files: list[PurePosixPath]) -> set[PurePosixPath]:
        return {f.parent for f in files if f.name == "__init__.py"}
