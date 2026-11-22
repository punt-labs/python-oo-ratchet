"""The in-tree layers baseline: the import edges allowed to stay in violation."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Self

from oo_ratchet.design.layer_edges import Edge

logger = logging.getLogger(__name__)


class LayersBaselineError(Exception):
    """A layers baseline could not be parsed, in the tree or at a git ref."""


class LayersBaseline:
    """Read and write ``.oo-layers-baseline.json``.

    The file maps each source module to the sorted modules it may keep
    importing against the rules, so a diff shows exactly which edge moved.
    """

    _path: Path
    _edges: frozenset[Edge]

    FILENAME: str = ".oo-layers-baseline.json"

    def __new__(cls, root: Path) -> Self:
        self = super().__new__(cls)
        self._path = root / cls.FILENAME
        text = self._path.read_text() if self._path.exists() else None
        self._edges = frozenset() if text is None else cls.parse(text, str(self._path))
        return self

    @property
    def path(self) -> Path:
        """Return the on-disk baseline path."""
        return self._path

    @property
    def exists(self) -> bool:
        """Return whether the baseline file is present on disk."""
        return self._path.exists()

    @property
    def edges(self) -> frozenset[Edge]:
        """Return the baselined violating edges."""
        return self._edges

    @staticmethod
    def parse(text: str, label: str) -> frozenset[Edge]:
        """Parse baseline JSON read from ``label``, or raise ``LayersBaselineError``."""
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError as exc:
            msg = f"unreadable layers baseline {label}: {exc}"
            raise LayersBaselineError(msg) from exc
        if not isinstance(loaded, dict) or not all(
            isinstance(targets, list) and all(isinstance(t, str) for t in targets)
            for targets in loaded.values()
        ):
            msg = f"layers baseline {label} must map a module to a list of modules"
            raise LayersBaselineError(msg)
        return frozenset(Edge(s, t) for s, targets in loaded.items() for t in targets)

    def scoped(self, package: str) -> frozenset[Edge]:
        """Return the baselined edges whose importing module is in ``package``."""
        return frozenset(e for e in self._edges if e.within(package))

    def raw(self) -> str | None:
        """Return the file text, or ``None`` when there is no file."""
        return self._path.read_text() if self._path.exists() else None

    def restore(self, text: str | None) -> None:
        """Put back what ``raw`` returned, deleting the file if there was none."""
        if text is None:
            self._path.unlink(missing_ok=True)
            self._edges = frozenset()
            return
        self._write(text)
        self._edges = self.parse(text, str(self._path))

    def save(self, edges: frozenset[Edge]) -> None:
        """Write ``edges`` sorted by source and refresh the in-memory view."""
        grouped: defaultdict[str, list[str]] = defaultdict(list)
        for edge in sorted(edges):
            grouped[edge.source].append(edge.target)
        self._write(json.dumps(dict(grouped), indent=2) + "\n")
        self._edges = edges
        logger.info("Wrote layers baseline %s: %d edges", self._path, len(edges))

    def _write(self, text: str) -> None:
        """Replace the file atomically: write a sibling temp file, then rename it."""
        fd, name = tempfile.mkstemp(dir=self._path.parent, prefix=self.FILENAME + ".")
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(text)
            Path(name).replace(self._path)
        except OSError:
            Path(name).unlink(missing_ok=True)
            raise
