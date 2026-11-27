"""The layers gate's history: what the repository held at the comparison base."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Self

from oo_ratchet.core.domain.edges import EdgeBook
from oo_ratchet.core.domain.layer_config import LayerConfig, LayerConfigError
from oo_ratchet.core.domain.layer_table import LayerTable
from oo_ratchet.source_set import Source, SourceSet

from .edgeformats import EdgeFormat
from .edgemodules import BaseModules
from .gitrepo import GitRepo
from .packagetrees import PackageTree


class EdgeRepo:
    """Answer the layers gate's questions about a commit; implements ``EdgeHistory``.

    ``baseline`` is the baseline file's name at the repository root and ``src``
    the scanned package directory.
    """

    _git: GitRepo
    _root: Path
    _src: Source
    _baseline: str

    def __new__(cls, git: GitRepo, root: Path, src: Source, baseline: str) -> Self:
        self = super().__new__(cls)
        self._git = git
        self._root = root
        self._src = src
        self._baseline = baseline
        return self

    def resolve(self, ref: str | None) -> str | None:
        """Return the comparison base: ``ref``, else the merge base of main."""
        return self._git.resolve(ref)

    def adopted_at(self, ref: str) -> bool:
        """Return whether a layers baseline is committed at ``ref``."""
        return self._git.adopted_at(ref)

    def head(self) -> str | None:
        """Return the abbreviated HEAD commit."""
        return self._git.head()

    def edges_at(self, ref: str) -> EdgeBook | None:
        """Return the baseline committed at ``ref``, ``None`` if absent."""
        text = self._git.show(ref, self._baseline)
        if text is None:
            return None
        return EdgeFormat.decode(text, f"{ref}:{self._baseline}")

    def has_package(self, ref: str, package: str) -> bool:
        """Return whether the package shows any trace at ``ref``.

        A trace is a top-level package directory of that name anywhere in the
        tree, or anything at the scanned directory's real path (a symlink, or a
        package at the repository root).
        """
        tree = PackageTree.base(ref, self._root)
        real = SourceSet.path(self._src).resolve().relative_to(self._root.resolve())
        return tree.package_at(package) or tree.path_at(real.as_posix())

    def policy_at(
        self, ref: str, config_path: Path | None, *, strict: bool
    ) -> LayerConfig | None:
        """Return the config committed at ``ref`` in the pyproject the scan used.

        With ``strict`` a ref that has no layer config there cannot be compared
        and the check fails; without it (a package new in this change) there is
        nothing to compare and ``None`` is returned. A config outside the
        repository always fails.
        """
        if config_path is None:
            return None
        try:
            rel = config_path.resolve().relative_to(self._root.resolve())
        except ValueError as exc:
            msg = f"layer config {config_path} is outside {self._root}"
            raise LayerConfigError(msg) from exc
        path = rel.as_posix()
        text = self._git.show(ref, path)
        config = LayerTable.from_text(text, f"{ref}:{path}").config() if text else None
        if config is None and strict:
            where = f"{ref[:10]}:{path}"
            msg = f"no layer config at the base ({where}) but a baseline exists"
            raise LayerConfigError(msg)
        return config

    def shared_at(self, ref: str, modules: Iterable[str], package: str) -> list[str]:
        """Return the ``modules`` that also existed at ``ref``."""
        return BaseModules(self._root, self._src).shared(modules, ref, package)
