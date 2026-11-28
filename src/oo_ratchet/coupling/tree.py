"""One aggregate coupling input, including the legacy single-file view."""

from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Self

from oo_ratchet.source_set import Source, SourceSelection


class CouplingTree:
    """Own discovery of the files a coupling scan covers."""

    _source: SourceSelection
    _file: Path | None

    def __new__(cls, target: Source) -> Self:
        self = super().__new__(cls)
        source = SourceSelection(target)
        self._file = source.file
        self._source = SourceSelection(self._file.parent if self._file else source)
        return self

    @property
    def source(self) -> SourceSelection:
        """Return the namespace-wide source selection."""
        return self._source

    @property
    def is_file(self) -> bool:
        """Return whether the target is one legacy file, not a package tree."""
        return self._file is not None

    @cached_property
    def modules(self) -> frozenset[str]:
        """Return every namespace-relative module key."""
        return frozenset(map(self._source.key_for, self._source.files()))

    @property
    def files(self) -> list[Path]:
        """Return selected files, not siblings of a legacy file target."""
        return [self._file] if self._file else self._source.files()
