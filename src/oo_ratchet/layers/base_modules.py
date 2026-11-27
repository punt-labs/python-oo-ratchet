"""The modules the scanned package had at the merge base."""

from __future__ import annotations

import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Self

from oo_ratchet.coupling.gitio import GitError
from oo_ratchet.design.layer_config import LayerConfig
from oo_ratchet.source_set import Source, SourceSet
from oo_ratchet.suppression.gitio import GitError as ArchiveError
from oo_ratchet.suppression.gitio import GitRepo

from .scan import LayerScan

__all__ = ["BaseModules", "GitError"]


class BaseModules:
    """Name the modules of a package as the base commit held them.

    The base tree is exported from git and scanned by the same ``LayerScan``
    that names the current modules, so the two sides agree on module names,
    including namespace portions and source moves.
    """

    _root: Path
    _src: Source
    _git: GitRepo

    def __new__(cls, root: Path, src: Source) -> Self:
        self = super().__new__(cls)
        self._root = root
        self._src = src
        self._git = GitRepo(root)
        return self

    def shared(
        self, modules: Iterable[str], base: str, config: LayerConfig
    ) -> list[str]:
        """Return the ``modules`` that also existed at ``base``.

        A package absent at ``base`` has no shared modules. ``config`` only
        lets the base scan run; it does not change module names.
        """
        try:
            was = SourceSet(self._src).rescan(
                base,
                self._git,
                lambda ref, target: self._single(ref, target, config),
                lambda target, _tree: frozenset(LayerScan(target, config).modules),
                lambda names, _old, _new: names,
            )
        except ArchiveError as exc:
            raise GitError(str(exc)) from exc
        return [m for m in modules if m in (was or frozenset())]

    def _single(
        self, ref: str, target: Path, config: LayerConfig
    ) -> frozenset[str] | None:
        rel = target.resolve().relative_to(self._root.resolve()).as_posix()
        if not self._git.path_exists_at_ref(ref, rel):
            return None
        with tempfile.TemporaryDirectory() as tmp:
            self._git.archive_paths(ref, [rel], Path(tmp))
            return frozenset(LayerScan(Path(tmp) / rel, config).modules)
