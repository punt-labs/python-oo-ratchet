"""A work tree already scored once: the ``SourceReader`` of a gate run."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from oo_ratchet.core.domain.scores import Measurement


class ScoredTree:
    """Answer a gate's questions about a tree scored before the gate started.

    The gate's CLI scores the tree once, to render views and to validate its
    input; this adapter hands that measurement to the operations instead of
    scanning again. ``key`` names a scored file by any spelling a person
    typed: repo-relative, absolute, or relative to the working directory.
    """

    _root: Path
    _measurement: Measurement

    def __new__(cls, root: Path, measurement: Measurement) -> Self:
        self = super().__new__(cls)
        self._root = root
        self._measurement = measurement
        return self

    def measure(self) -> Measurement:
        """Return the scan the gate started with."""
        return self._measurement

    def exists(self, path: str) -> bool:
        """Return whether the repo-relative ``path`` is on disk."""
        return (self._root / path).exists()

    def key(self, requested: str) -> str:
        """Return the scored key ``requested`` names, else ``requested`` itself.

        A relative spelling is tried against the repository root first, then
        the working directory.
        """
        scored = self._measurement.paths
        if requested in scored:
            return requested
        index = {(self._root / key).resolve(): key for key in scored}
        path = Path(requested)
        if not path.is_absolute():
            hit = index.get((self._root / path).resolve())
            if hit is not None:
                return hit
        return index.get(path.resolve(), requested)
