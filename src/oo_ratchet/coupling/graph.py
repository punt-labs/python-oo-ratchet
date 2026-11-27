"""Build the internal import graph and find the modules caught in cycles."""

from __future__ import annotations

import ast
from typing import Self

from oo_ratchet.source_set import SourceSet

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
    def build(cls, source: SourceSet, modules: frozenset[str]) -> Self:
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
        for component in self._components():
            node = next(iter(component))
            if len(component) > 1 or node in self._edges.get(node, set()):
                in_cycle.update(component)
        return in_cycle

    def _components(self) -> list[set[str]]:
        """Return the strongly connected components (iterative Tarjan, sorted walk)."""
        index_of: dict[str, int] = {}
        lowlink: dict[str, int] = {}
        stack: list[str] = []
        on_stack: set[str] = set()
        sccs: list[set[str]] = []
        for root in sorted(self._edges):
            if root in index_of:
                continue
            work = [(root, self._enter(root, index_of, lowlink, stack, on_stack), 0)]
            while work:
                node, neighbors, i = work[-1]
                if i < len(neighbors):
                    work[-1] = (node, neighbors, i + 1)
                    nxt = neighbors[i]
                    if nxt not in index_of:
                        entered = self._enter(nxt, index_of, lowlink, stack, on_stack)
                        work.append((nxt, entered, 0))
                    elif nxt in on_stack:
                        lowlink[node] = min(lowlink[node], index_of[nxt])
                    continue
                work.pop()
                if work:
                    parent = work[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[node])
                if lowlink[node] == index_of[node]:
                    sccs.append(self._pop_component(node, stack, on_stack))
        return sccs

    def _enter(
        self,
        node: str,
        index_of: dict[str, int],
        lowlink: dict[str, int],
        stack: list[str],
        on_stack: set[str],
    ) -> list[str]:
        index_of[node] = lowlink[node] = len(index_of)
        stack.append(node)
        on_stack.add(node)
        return sorted(n for n in self._edges.get(node, set()) if n in self._edges)

    @staticmethod
    def _pop_component(node: str, stack: list[str], on_stack: set[str]) -> set[str]:
        component: set[str] = set()
        while True:
            member = stack.pop()
            on_stack.discard(member)
            component.add(member)
            if member == node:
                return component
