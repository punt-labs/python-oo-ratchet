"""Stable package-relative keys over one resolved source selection."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from oo_ratchet.source_set import Source, SourceSet


class PackageLayout:
    """Keep import identity independent of source portions' physical paths."""

    _source: SourceSet
    _modules: frozenset[str]

    def __new__(cls, directory: Source) -> Self:
        self = super().__new__(cls)
        self._source = SourceSet(directory)
        self._modules = frozenset(self.key_for(p) for p in self.root_files())
        return self

    @property
    def name(self) -> str:
        """Return the namespace spelling used to resolve coupling imports."""
        return self._source.name

    @property
    def root(self) -> Path:
        """Return the physical common ancestor of the selection."""
        return self._source.anchor

    @property
    def package_name(self) -> str:
        """Return the logical name, preserving legacy symlink spelling."""
        return self._source.package_name

    @property
    def modules(self) -> frozenset[str]:
        """Return every namespace-relative module key."""
        return self._modules

    def root_files(self) -> list[Path]:
        """Return each selected physical file once."""
        return self._source.files()

    def key_for(self, py_file: Path) -> str:
        """Return the key paired with ``name`` to form the dotted import name."""
        return self._source.key_for(py_file)

    def relative_path(self, path: Path) -> Path:
        """Return the source-relative spelling used for shadowed modules."""
        return self._source.relative_path(path)

    def contains(self, component: str) -> bool:
        """Return whether a source portion contains this subdirectory."""
        return self._source.contains(component)

    def package_dirs(self) -> list[Path]:
        """Return non-root package directories across every portion."""
        return self._source.package_dirs()

    @staticmethod
    def _parts_to_key(parts: tuple[str, ...]) -> str:
        return SourceSet.parts_to_key(parts)
