"""The names a package ``__init__`` can bind from other modules, over-approximated."""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Mapping
from typing import Self

from oo_ratchet.design.layer_violations import Site

type Origin = tuple[str, str]


class Reexports:
    """Collect every import in an ``__init__``, wherever it sits and whatever follows.

    A name imported from a package counts as an import of each module the
    package's ``__init__`` binds that name from on any path: imports anywhere in
    the file count (module scope, any nested block, function bodies), and no
    rebinding, ``del``, annotation or ``__all__`` ever removes one. A wildcard
    ``from X import *`` makes every name imported from the package an import of
    ``X`` too. The result may name a dependency the code never makes; the
    author restructures, the gate never passes a forbidden import.
    """

    _named: defaultdict[str, set[Origin]]
    _wildcards: set[str]

    def __new__(
        cls,
        tree: ast.Module,
        rows: list[tuple[Site, str, str]],
        trees: Mapping[str, ast.Module],
    ) -> Self:
        self = super().__new__(cls)
        resolved: defaultdict[int, dict[str, str]] = defaultdict(dict)
        for node, symbol, target in rows:
            resolved[id(node)][symbol] = target
        self._named = defaultdict(set)
        self._wildcards = set()
        for item in ast.walk(tree):
            if isinstance(item, ast.ImportFrom):
                self._from(item, resolved[id(item)])
            elif isinstance(item, ast.Import):
                self._import(item, trees)
        return self

    def get(self, name: str) -> frozenset[Origin]:
        """Return every ``(module, original name)`` ``name`` can come from."""
        wild = {(module, name) for module in self._wildcards}
        return frozenset(self._named.get(name, set()) | wild)

    def _from(self, node: ast.ImportFrom, found: dict[str, str]) -> None:
        if "*" in found:
            self._wildcards.add(found["*"])
        for alias in node.names:
            if alias.name in found and alias.name != "*":
                bound = alias.asname or alias.name
                self._named[bound].add((found[alias.name], alias.name))

    def _import(self, node: ast.Import, trees: Mapping[str, ast.Module]) -> None:
        for alias in node.names:
            if alias.asname and alias.name in trees:
                self._named[alias.asname].add((alias.name, ""))
