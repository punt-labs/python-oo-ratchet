"""Cycle detection for the diagram scripts: strongly connected components of a digraph."""

from __future__ import annotations

from collections.abc import Iterable, Mapping


def strongly_connected(graph: Mapping[str, Iterable[str]]) -> list[list[str]]:
    """Tarjan's algorithm. Returns each cyclic component (more than one node, or a
    node that imports itself) as a sorted member list. The members of a component
    reach one another through some path; they do not all import one another."""
    succ = {v: set(ws) for v, ws in graph.items()}
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    out: list[list[str]] = []

    def visit(v: str) -> None:
        index[v] = low[v] = len(index)
        stack.append(v)
        on_stack.add(v)
        for w in sorted(succ.get(v, ())):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1 or v in succ.get(v, ()):
                out.append(sorted(comp))

    for v in sorted(succ):
        if v not in index:
            visit(v)
    return sorted(out)


def has_cycle(pairs: Iterable[tuple[str, str]]) -> bool:
    """True when the edge list contains a cycle of any length."""
    succ: dict[str, set[str]] = {}
    for a, b in pairs:
        succ.setdefault(a, set()).add(b)
    return bool(strongly_connected(succ))
