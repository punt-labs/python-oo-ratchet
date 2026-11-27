"""The modules the scanned package had at the merge base, from its committed tree."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Self

from oo_ratchet.coupling.gitio import GitError
from oo_ratchet.source_set import Source, SourceSet

from .gitio import LayersGit
from .scan import LayersScanError

__all__ = ["BaseModules", "GitError"]


class BaseModules:
    """Name the modules a package had at a ref, read from ``git ls-tree``.

    Tracked ``.py`` files are listed whatever ``export-ignore`` says, and no
    scan or validation runs on them, so a base that held only an initializer
    is fine. Paths become names by the working tree's own rule
    (``SourceSet.parts_to_key``), with the same package or namespace name.
    A package whose directory has no ``__init__.py`` at the base is looked up
    by import name: one match is the relocated package, several are refused.
    """

    _root: Path
    _src: Source
    _git: LayersGit

    def __new__(cls, root: Path, src: Source, git: LayersGit) -> Self:
        self = super().__new__(cls)
        self._root = root
        self._src = src
        self._git = git
        return self

    def shared(self, modules: Iterable[str], base: str, package: str) -> list[str]:
        """Return the ``modules`` that also existed at ``base``.

        ``package`` is the current import name of the package (the namespace in
        namespace mode). A package absent at ``base`` has no shared modules.
        """
        files = self._tracked_python(base)
        known = {
            name
            for prefix in self._prefixes(files, package, base)
            for name in self._names(files, prefix, package)
        }
        return [m for m in modules if m in known]

    def _tracked_python(self, base: str) -> list[PurePosixPath]:
        out = self._git._git(["ls-tree", "-r", "--name-only", "-z", base])
        if out is None:
            raise GitError(f"git ls-tree -r {base} failed")
        return [PurePosixPath(p) for p in out.split("\0") if p.endswith(".py")]

    def _prefixes(
        self, files: list[PurePosixPath], package: str, base: str
    ) -> list[PurePosixPath]:
        """Return the base directory of each source portion, repo-relative."""
        portions = SourceSet(self._src).roots
        here = [self._relative(p) for p in portions]
        if SourceSet(self._src).namespace is not None:
            return [q for p in here for q in self._portion(files, p, base)]
        if self._holds(files, here[0]):
            return here
        return self._relocated(files, package)

    def _portion(
        self, files: list[PurePosixPath], portion: PurePosixPath, base: str
    ) -> list[PurePosixPath]:
        """Return where a namespace portion was: here, or where git moved it from."""
        if any(f.is_relative_to(portion) for f in files):
            return [portion]
        out = self._git._git(["diff", "--name-status", "-M", base])
        if out is None:
            raise GitError(f"git diff -M {base} failed")
        moved = {self._old_prefix(row, portion) for row in out.splitlines()}
        return sorted(p for p in moved if p is not None)

    @staticmethod
    def _old_prefix(row: str, portion: PurePosixPath) -> PurePosixPath | None:
        """Return the old directory of ``portion`` if ``row`` renamed a file in it."""
        kind, *paths = row.split("\t")
        if not kind.startswith("R") or len(paths) != 2:
            return None
        old, new = (PurePosixPath(x) for x in paths)
        if not new.is_relative_to(portion):
            return None
        inner = new.relative_to(portion).parts
        return (
            old.parents[len(inner) - 1] if old.parts[-len(inner) :] == inner else None
        )

    def _relocated(
        self, files: list[PurePosixPath], package: str
    ) -> list[PurePosixPath]:
        found = [
            f.parent
            for f in files
            if f.name == "__init__.py" and f.parent.name == package
        ]
        if len(found) > 1:
            where = ", ".join(sorted(str(p) for p in found))
            msg = (
                f"cannot tell where package {package!r} was at the base: "
                f"more than one directory holds it ({where})"
            )
            raise LayersScanError(msg)
        return found

    @staticmethod
    def _holds(files: list[PurePosixPath], prefix: PurePosixPath) -> bool:
        return prefix / "__init__.py" in files

    @staticmethod
    def _names(
        files: list[PurePosixPath], prefix: PurePosixPath, package: str
    ) -> set[str]:
        keys = (
            SourceSet.parts_to_key(f.relative_to(prefix).with_suffix("").parts)
            for f in files
            if f.is_relative_to(prefix)
        )
        return {package if k == "__init__" else f"{package}.{k}" for k in keys}

    def _relative(self, portion: Path) -> PurePosixPath:
        return PurePosixPath(portion.resolve().relative_to(self._root.resolve()))
