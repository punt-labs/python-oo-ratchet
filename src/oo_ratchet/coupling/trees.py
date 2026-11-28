"""Read a source tree from disk and score it for coupling."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING, Self

from .config import CouplingConfig
from .graph import ImportGraph
from .imports import ImportResolver
from .metrics import ModuleCouplingMetrics
from .packageinit import PackageInit
from .packages import PackageMetrics, PackageScorer
from .scorer import CouplingScorer
from .tree import CouplingTree

if TYPE_CHECKING:
    from oo_ratchet.source_set import Source


class TreeScan:
    """Read a ``CouplingTree`` and score it with its import graph.

    Keys are normalized repo-relative (POSIX) against ``root`` so scorer
    output, baseline keys, and diff paths all intersect cleanly regardless
    of how the target path was spelled on the command line.
    """

    _tree: CouplingTree
    _root: Path
    _config: CouplingConfig
    _graph: ImportGraph

    def __new__(cls, tree: CouplingTree, root: Path, config: CouplingConfig) -> Self:
        self = super().__new__(cls)
        self._tree = tree
        self._root = root
        self._config = config
        self._graph = ImportGraph({} if tree.is_file else self._read_edges())
        return self

    @property
    def graph(self) -> ImportGraph:
        """Return the import graph across every selected portion."""
        return self._graph

    def scorer(self) -> CouplingScorer:
        """Return the scorer over every file and sub-package of the tree."""
        return CouplingScorer(self._results(), self._packages(), self._config.caps)

    def _results(self) -> list[dict[str, float | int | str]]:
        cycle = frozenset(self._graph.cycle_members())
        return [self._safe_score(f, cycle) for f in self._tree.files]

    def _packages(self) -> tuple[PackageMetrics, ...]:
        """Return package metrics only for whole-tree scans."""
        if self._tree.is_file:
            return ()
        source = self._tree.source
        inits = tuple(self._package_init(d) for d in source.package_dirs())
        return tuple(PackageScorer(inits, self._graph).score())

    def _read_edges(self) -> dict[str, set[str]]:
        """Parse every module of the selection into its internal import edges."""
        source = self._tree.source
        edges: dict[str, set[str]] = {}
        for py_file in sorted(source.files()):
            key = source.key_for(py_file)
            try:
                tree = ast.parse(py_file.read_text(), filename=str(py_file))
            except (SyntaxError, OSError, UnicodeDecodeError):
                # Unparseable/unreadable modules are omitted from the import
                # graph; the scorer records the same file as an error so the
                # ratchet still fails closed on it when it is touched.
                continue
            resolver = ImportResolver(
                key,
                self._tree.modules,
                source.name,
                is_package=py_file.name == "__init__.py",
            )
            edges[key] = resolver.internal_imports(tree)
        return edges

    def _package_init(self, pkg_dir: Path) -> PackageInit:
        init = pkg_dir / "__init__.py"
        name = self._tree.source.key_for(init)
        if not init.exists():
            return PackageInit(name, None)
        try:
            return PackageInit(name, init.read_text())
        except (OSError, UnicodeDecodeError):
            return PackageInit(name, None)

    def _safe_score(
        self, py_file: Path, cycle: frozenset[str]
    ) -> dict[str, float | int | str]:
        key = self._normalize(py_file)
        try:
            tree = ast.parse(py_file.read_text(), filename=str(py_file))
        except (SyntaxError, OSError, UnicodeDecodeError) as exc:
            # A file that cannot be read or decoded is scored as an error, like a
            # syntax error: the ratchet fails on it if it is a touched file
            # (fail-closed), rather than crashing the whole scoring pass.
            return {"file": key, "error": str(exc)}
        source = self._tree.source
        mod_key = source.key_for(py_file)
        resolver = ImportResolver(
            mod_key,
            self._tree.modules,
            source.name,
            is_package=py_file.name == "__init__.py",
        )
        metrics = ModuleCouplingMetrics(
            key, tree, resolver, self._config.stateless_values
        ).compute()
        metrics["circular_imports"] = 1 if mod_key in cycle else 0
        return metrics

    def _normalize(self, path: Path) -> str:
        resolved = path.resolve()
        try:
            return resolved.relative_to(self._root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()


def score_path(
    target: Source, repo_root: Path | None = None, config: CouplingConfig | None = None
) -> CouplingScorer:
    """Read ``target`` from disk and return its coupling scorer."""
    root = repo_root if repo_root is not None else Path.cwd()
    settings = config if config is not None else CouplingConfig()
    return TreeScan(CouplingTree(target), root, settings).scorer()
