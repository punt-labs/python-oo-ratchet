"""Package-level import graph for oo_ratchet: edges, cycles, and edge counts.

A package is a direct subpackage of the root (`oo`, `design`, ...). Modules that sit
directly in the root package belong to `<entry>` (`__main__`, `gates`) or `<root>`
(everything else); `--one-root` puts them all in `<root>`, which shows the cycle
the entry modules close through the shared root package. The module-to-package map is built
from the scanned files, so a source and a destination are grouped the same way.
Cycles are the strongly connected components of the package graph, of any length.
"""

from __future__ import annotations

import ast
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(sys.argv[1])  # .../src/oo_ratchet
ONE_ROOT = "--one-root" in sys.argv[2:]
PKG = ROOT.name
ROOT_GROUP = "<root>"
ENTRY_GROUP = "<entry>"
ENTRY_MODULES = {"__main__", "gates"}


def module_name(path: Path) -> str:
    rel = path.relative_to(ROOT.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def group_of_path(path: Path) -> str:
    """The direct subpackage holding this file. Root-level files are ENTRY_GROUP
    (the dispatcher and the gate registry, which import every gate) or ROOT_GROUP
    (the shared modules every gate imports); with --one-root they are all ROOT_GROUP."""
    rel = path.relative_to(ROOT).parts
    if len(rel) > 1:
        return rel[0]
    if not ONE_ROOT and path.stem in ENTRY_MODULES:
        return ENTRY_GROUP
    return ROOT_GROUP


def resolve(node: ast.ImportFrom, here: str, is_pkg: bool) -> str | None:
    if node.level == 0:
        return node.module
    base = here.split(".")
    if not is_pkg:
        base = base[:-1]
    base = base[: len(base) - (node.level - 1)]
    return ".".join(base + ([node.module] if node.module else []))


def strongly_connected(graph: dict[str, set[str]]) -> list[list[str]]:
    """Tarjan's algorithm: components with more than one node, or a self-loop."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    out: list[list[str]] = []

    def visit(v: str) -> None:
        index[v] = low[v] = len(index)
        stack.append(v)
        on_stack.add(v)
        for w in graph.get(v, set()):
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
            if len(comp) > 1 or v in graph.get(v, set()):
                out.append(sorted(comp))

    for v in sorted(graph):
        if v not in index:
            visit(v)
    return out


files = sorted(ROOT.rglob("*.py"))
group_of_module = {module_name(p): group_of_path(p) for p in files}


def group_of_import(target: str) -> str | None:
    """Group of the longest scanned module that is `target` or a parent of it."""
    parts = target.split(".")
    while parts:
        name = ".".join(parts)
        if name in group_of_module:
            return group_of_module[name]
        parts.pop()
    return None


edges: Counter[tuple[str, str]] = Counter()
examples: dict[tuple[str, str], list[str]] = defaultdict(list)
for path in files:
    here = module_name(path)
    src = group_of_path(path)
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        targets: list[str] = []
        if isinstance(node, ast.Import):
            targets = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mod = resolve(node, here, path.name == "__init__.py")
            if mod:
                targets = [mod]
        for t in targets:
            if not t.startswith(PKG + "."):
                continue
            dst = group_of_import(t)
            if dst is not None and dst != src:
                edges[(src, dst)] += 1
                examples[(src, dst)].append(f"{here} -> {t}")

graph: dict[str, set[str]] = defaultdict(set)
for (a, b) in edges:
    graph[a].add(b)

print("package edges (count):")
for (a, b), n in sorted(edges.items()):
    print(f"  {a:12} -> {b:12} {n}")

cycles = strongly_connected(graph)
print(f"cycles: {len(cycles)}")
for comp in cycles:
    print(f"  {' <-> '.join(comp)}")
    for a in comp:
        for b in comp:
            for e in examples.get((a, b), [])[:2]:
                print(f"     {e}")
