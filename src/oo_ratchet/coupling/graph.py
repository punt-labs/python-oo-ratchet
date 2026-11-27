"""Build the internal import graph and find the modules caught in cycles."""

from __future__ import annotations

import ast
from typing import Self

from oo_ratchet.core.domain.modulesource import ModuleSource

from .components import Components
from .imports import ImportResolver


class ImportGraph:
    """A directed graph of internal package imports, keyed by module.

    Nodes are the source's dotted module keys; an edge ``a -> b`` means module
    ``a`` imports module ``b`` from the same package. ``cycle_members`` returns
    every node on any directed cycle, which the scorer maps to the
    ``circular_imports`` metric.
    """

    _edges: dict[str, set[str]]

    def __new__(cls, edges: dict[str, set[str]]) -> Self:
        self = super().__new__(cls)
        self._edges = edges
        return self

    @classmethod
    def build(cls, source: ModuleSource, modules: frozenset[str]) -> Self:
        """Parse every module of ``source`` into an import graph."""
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
                modules,
                source.name,
                is_package=py_file.name == "__init__.py",
            )
            edges[key] = resolver.internal_imports(tree)
        return cls(edges)

    @property
    def edges(self) -> dict[str, set[str]]:
        """Return the adjacency map of module key to imported keys."""
        return self._edges

    def neighbors(self, node: str) -> set[str]:
        """Return the modules imported by ``node`` (empty if unknown)."""
        return self._edges.get(node, set())

    def cycle_members(self) -> set[str]:
        """Return every node on any import cycle: its SCC has 2+ members or a self-loop.

        Strongly connected components do not depend on traversal order, so no
        cycle member is missed when the walk reaches it through an
        already-finished node (the DFS back-edge bug fixed in lux PR #466).
        """
        in_cycle: set[str] = set()
        for component in Components(self._edges).find():
            node = next(iter(component))
            if len(component) > 1 or node in self._edges.get(node, set()):
                in_cycle.update(component)
        return in_cycle
