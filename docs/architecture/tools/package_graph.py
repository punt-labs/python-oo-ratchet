"""Import graph for oo_ratchet: package edges, package cycles, and module cycles.

A package is a direct subpackage of the root (`oo`, `design`, ...). Modules that sit
directly in the root package belong to `<entry>` (`__main__`, `gates`) or `<root>`
(everything else); `--one-root` puts them all in `<root>`, which shows the cycle
the entry modules close through the shared root package.
The module-to-package map is built from the scanned files, so a source and a
destination are grouped the same way. Cycles are strongly connected components of
any length, reported at package level and at module level.
"""

from __future__ import annotations

import ast
import sys
from collections import Counter, defaultdict
from pathlib import Path

from graph_tools import strongly_connected

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
    """The direct subpackage holding this file, or the entry/root group for
    root-level files (both are ROOT_GROUP with --one-root)."""
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


files = sorted(ROOT.rglob("*.py"))
path_of_module = {module_name(p): p for p in files}


def scanned_module(target: str) -> str | None:
    """The longest scanned module that is `target` or a parent of it."""
    parts = target.split(".")
    while parts:
        name = ".".join(parts)
        if name in path_of_module:
            return name
        parts.pop()
    return None


def imported_modules(node: ast.AST, here: str, is_pkg: bool) -> list[str]:
    """Scanned modules an import statement loads. `from pkg import sub` counts
    `pkg.sub` when `sub` is itself a scanned module."""
    if isinstance(node, ast.Import):
        found = [scanned_module(a.name) for a in node.names]
    elif isinstance(node, ast.ImportFrom):
        mod = resolve(node, here, is_pkg)
        if not mod:
            return []
        found = [f"{mod}.{a.name}" if f"{mod}.{a.name}" in path_of_module
                 else scanned_module(mod) for a in node.names]
    else:
        return []
    return sorted({m for m in found if m is not None and m.startswith(PKG + ".")})


edges: Counter[tuple[str, str]] = Counter()
examples: dict[tuple[str, str], list[str]] = defaultdict(list)
module_graph: dict[str, set[str]] = defaultdict(set)
for path in files:
    here = module_name(path)
    src = group_of_path(path)
    is_pkg = path.name == "__init__.py"
    for node in ast.walk(ast.parse(path.read_text())):
        for target in imported_modules(node, here, is_pkg):
            if target != here:
                module_graph[here].add(target)
            dst = group_of_path(path_of_module[target])
            if dst != src:
                edges[(src, dst)] += 1
                examples[(src, dst)].append(f"{here} -> {target}")

package_graph: dict[str, set[str]] = defaultdict(set)
for (a, b) in edges:
    package_graph[a].add(b)

print("package edges (count):")
for (a, b), n in sorted(edges.items()):
    print(f"  {a:12} -> {b:12} {n}")

cycles = strongly_connected(package_graph)
print(f"package cycles: {len(cycles)}")
for comp in cycles:
    print(f"  component: {', '.join(comp)}")
    for a in comp:
        for b in comp:
            for e in examples.get((a, b), [])[:2]:
                print(f"     {e}")

module_cycles = strongly_connected(module_graph)
print(f"module cycles: {len(module_cycles)} "
      f"(over {len(files)} modules, package __init__ imports included)")
for comp in module_cycles:
    print(f"  component: {', '.join(comp)}")
