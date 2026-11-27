"""Package-level import graph for oo_ratchet: edges, cycles, and edge counts."""

from __future__ import annotations

import ast
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(sys.argv[1])  # .../src/oo_ratchet
PKG = ROOT.name


def package_of(module: str) -> str:
    parts = module.split(".")
    return parts[1] if len(parts) > 2 else "<root>"


def module_name(path: Path) -> str:
    rel = path.relative_to(ROOT.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def resolve(node: ast.ImportFrom, here: str, is_pkg: bool) -> str | None:
    if node.level == 0:
        return node.module
    base = here.split(".")
    if not is_pkg:
        base = base[:-1]
    base = base[: len(base) - (node.level - 1)]
    return ".".join(base + ([node.module] if node.module else []))


edges: Counter[tuple[str, str]] = Counter()
examples: dict[tuple[str, str], list[str]] = defaultdict(list)
for path in ROOT.rglob("*.py"):
    here = module_name(path)
    src_pkg = package_of(here + ".x") if path.name == "__init__.py" else package_of(here)
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
            dst_pkg = package_of(t) if t.count(".") >= 2 else package_of(t + ".x")
            if dst_pkg != src_pkg:
                edges[(src_pkg, dst_pkg)] += 1
                examples[(src_pkg, dst_pkg)].append(f"{here} -> {t}")

graph: dict[str, set[str]] = defaultdict(set)
for (a, b) in edges:
    graph[a].add(b)

print("package edges (count):")
for (a, b), n in sorted(edges.items()):
    print(f"  {a:12} -> {b:12} {n}")

print("cycles (pairs):")
for (a, b) in sorted(edges):
    if (b, a) in edges and a < b:
        print(f"  {a} <-> {b}")
        for e in examples[(a, b)][:4]:
            print(f"     {e}")
        for e in examples[(b, a)][:4]:
            print(f"     {e}")
