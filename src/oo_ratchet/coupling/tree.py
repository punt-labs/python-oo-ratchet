"""One aggregate coupling input, including the legacy single-file view."""

from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Self

from oo_ratchet.source_set import Source, SourceSet

from .graph import ImportGraph
from .packages import PackageMetrics, PackageScorer


class CouplingTree:
    """Own discovery and the complete graph before per-file metrics are scored."""

    _source: SourceSet
    _graph: ImportGraph
    _file: Path | None

    def __new__(cls, target: Source) -> Self:
        self = super().__new__(cls)
        source = SourceSet(target)
        self._file = source.file
        self._source = SourceSet(self._file.parent if self._file else source)
        self._graph = (
            ImportGraph({})
            if self._file
            else ImportGraph.build(self._source, self.modules)
        )
        return self

    @property
    def source(self) -> SourceSet:
        """Return the namespace-wide source selection."""
        return self._source

    @cached_property
    def modules(self) -> frozenset[str]:
        """Return every namespace-relative module key."""
        return frozenset(map(self._source.key_for, self._source.files()))

    @property
    def files(self) -> list[Path]:
        """Return selected files, not siblings of a legacy file target."""
        return [self._file] if self._file else self._source.files()

    @property
    def cycles(self) -> frozenset[str]:
        """Return cycle membership measured across all selected portions."""
        return frozenset(self._graph.cycle_members())

    @property
    def packages(self) -> tuple[PackageMetrics, ...]:
        """Return package metrics only for whole-tree scans."""
        return (
            ()
            if self._file
            else tuple(PackageScorer(self._source, self._graph).score())
        )
