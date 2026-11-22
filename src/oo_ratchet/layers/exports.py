"""The names a package ``__init__`` re-exports, from its module-scope flow."""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Mapping
from typing import Self

from oo_ratchet.design.layer_violations import Site

from .flow import BindingFlow, Bindings, Origin
from .public import PublicNames


class Reexports:
    """Map each name an ``__init__`` can leave bound to an import to its origins.

    The module-scope flow decides which bindings survive (see ``BindingFlow``).
    ``from .a import X`` binds ``X`` to ``(module a, "X")``; ``import pkg.a as X``
    binds it to ``(module pkg.a, "")``; ``from .a import *`` binds every public
    name of ``a`` (its literal ``__all__``, else its names without a leading
    underscore) to ``(module a, name)``.
    """

    _rows: defaultdict[int, dict[str, str]]
    _trees: Mapping[str, ast.Module]
    _names: Bindings

    def __new__(
        cls,
        tree: ast.Module,
        rows: list[tuple[Site, str, str]],
        trees: Mapping[str, ast.Module],
    ) -> Self:
        self = super().__new__(cls)
        self._rows = defaultdict(dict)
        for node, symbol, target in rows:
            self._rows[id(node)][symbol] = target
        self._trees = trees
        self._names = BindingFlow(self._imports).run(tree.body)
        return self

    def get(self, name: str) -> frozenset[Origin]:
        """Return the ``(module, original name)`` origins of a re-exported name."""
        return self._names.get(name, frozenset())

    def _imports(self, stmt: ast.Import | ast.ImportFrom) -> Bindings:
        if isinstance(stmt, ast.Import):
            return self._import(stmt)
        found = self._rows[id(stmt)]
        bound: Bindings = {}
        for alias in stmt.names:
            if alias.name == "*":
                bound.update(self._wildcard(found.get("*")))
            else:
                origin = (
                    {(found[alias.name], alias.name)} if alias.name in found else set()
                )
                bound[alias.asname or alias.name] = frozenset(origin)
        return bound

    def _import(self, stmt: ast.Import) -> Bindings:
        bound: Bindings = {}
        for alias in stmt.names:
            module = alias.name if alias.asname and alias.name in self._trees else None
            origin = frozenset({(module, "")}) if module else frozenset()
            bound[alias.asname or alias.name.split(".")[0]] = origin
        return bound

    def _wildcard(self, target: str | None) -> Bindings:
        if target is None or target not in self._trees:
            return {}
        return {
            name: frozenset({(target, name)})
            for name in PublicNames.of(self._trees[target])
        }
