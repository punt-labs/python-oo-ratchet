"""The OO gate's work tree: a ``SourceReader`` over one scoring run."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Self

from oo_ratchet.core.domain.scores import Measurement, Score

if TYPE_CHECKING:
    from oo_ratchet.oo.scorer import Scorer


class OoTree:
    """Answer the operations' questions about the scored tree.

    The tree is scored once, by the ``Scorer`` the gate built; every path is
    repo-relative POSIX.
    """

    _root: Path
    _measured: Measurement

    def __new__(cls, root: Path, scorer: Scorer, names: Sequence[str]) -> Self:
        self = super().__new__(cls)
        self._root = root
        self._measured = Measurement(
            tuple(
                Score(str(r["file"]), {k: float(r[k]) for k in names if k in r})
                for r in scorer.results
                if "error" not in r
            ),
            scorer.parse_errors,
        )
        return self

    def measure(self) -> Measurement:
        """Return the scores and the unparseable files."""
        return self._measured

    def exists(self, path: str) -> bool:
        """Return whether the repo-relative ``path`` is on disk."""
        return (self._root / path).exists()

    def key(self, requested: str) -> str:
        """Return the scored-file key any spelling of a path names.

        A scored key, an absolute path, a ``./`` prefix or a redundant segment
        all name the same file; a path relative to the working directory is the
        last resort. A path that names no scored file is returned unchanged.
        """
        keys = self._measured.paths
        if requested in keys:
            return requested
        index = {(self._root / key).resolve(): key for key in keys}
        path = Path(requested)
        if not path.is_absolute():
            hit = index.get((self._root / path).resolve())
            if hit is not None:
                return hit
        return index.get(path.resolve(), requested)
