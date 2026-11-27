"""Strongly connected components of an import graph (iterative Tarjan)."""

from __future__ import annotations

from typing import Self


class Components:
    """The strongly connected components of a module import graph.

    The walk is iterative and visits roots and neighbours in sorted order, so
    the result does not depend on dict ordering. One instance walks one graph.
    """

    _edges: dict[str, set[str]]
    _index_of: dict[str, int]
    _lowlink: dict[str, int]
    _stack: list[str]
    _on_stack: set[str]

    def __new__(cls, edges: dict[str, set[str]]) -> Self:
        self = super().__new__(cls)
        self._edges = edges
        self._index_of = {}
        self._lowlink = {}
        self._stack = []
        self._on_stack = set()
        return self

    def find(self) -> list[set[str]]:
        """Return the strongly connected components."""
        sccs: list[set[str]] = []
        for root in sorted(self._edges):
            if root in self._index_of:
                continue
            work = [(root, self._enter(root), 0)]
            while work:
                node, neighbors, i = work[-1]
                if i < len(neighbors):
                    work[-1] = (node, neighbors, i + 1)
                    self._visit(neighbors[i], node, work)
                    continue
                work.pop()
                if work:
                    parent = work[-1][0]
                    self._lowlink[parent] = min(
                        self._lowlink[parent], self._lowlink[node]
                    )
                if self._lowlink[node] == self._index_of[node]:
                    sccs.append(self._pop_component(node))
        return sccs

    def _visit(
        self, nxt: str, node: str, work: list[tuple[str, list[str], int]]
    ) -> None:
        if nxt not in self._index_of:
            work.append((nxt, self._enter(nxt), 0))
        elif nxt in self._on_stack:
            self._lowlink[node] = min(self._lowlink[node], self._index_of[nxt])

    def _enter(self, node: str) -> list[str]:
        self._index_of[node] = self._lowlink[node] = len(self._index_of)
        self._stack.append(node)
        self._on_stack.add(node)
        return sorted(n for n in self._edges.get(node, set()) if n in self._edges)

    def _pop_component(self, node: str) -> set[str]:
        component: set[str] = set()
        while True:
            member = self._stack.pop()
            self._on_stack.discard(member)
            component.add(member)
            if member == node:
                return component
