"""The names a package ``__init__`` re-exports, from its module-scope bindings."""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Container, Iterator
from typing import Self

from oo_ratchet.design.layer_violations import Site

_COMPOUND = ("body", "orelse", "finalbody")


class Reexports:
    """Map each name an ``__init__`` binds at module scope to what it came from.

    Statements are read in order, so a later assignment, ``def`` or ``class``
    of the same name ends the re-export. Imports inside functions or classes
    bind nothing at module scope and are ignored. ``from .a import X`` maps
    ``X`` to ``(module a, "X")``; ``import pkg.a as X`` maps ``X`` to
    ``(module pkg.a, "")``.
    """

    _names: dict[str, tuple[str, str]]

    def __new__(
        cls,
        tree: ast.Module,
        rows: list[tuple[Site, str, str]],
        known: Container[str],
    ) -> Self:
        self = super().__new__(cls)
        resolved: defaultdict[int, list[tuple[str, str]]] = defaultdict(list)
        for node, symbol, target in rows:
            resolved[id(node)].append((symbol, target))
        self._names = {}
        for stmt in cls._scope(tree.body):
            if isinstance(stmt, ast.ImportFrom):
                self._from(stmt, resolved[id(stmt)])
            elif isinstance(stmt, ast.Import):
                self._import(stmt, known)
            else:
                for name in cls._rebound(stmt):
                    self._names.pop(name, None)
        return self

    def get(self, name: str) -> tuple[str, str] | None:
        """Return ``(module, original name)`` for a re-exported ``name``."""
        return self._names.get(name)

    def _from(self, stmt: ast.ImportFrom, rows: list[tuple[str, str]]) -> None:
        by_symbol = dict(rows)
        for alias in stmt.names:
            bound = alias.asname or alias.name
            self._names.pop(bound, None)
            if alias.name in by_symbol:
                self._names[bound] = (by_symbol[alias.name], alias.name)

    def _import(self, stmt: ast.Import, known: Container[str]) -> None:
        for alias in stmt.names:
            bound = alias.asname or alias.name.split(".")[0]
            self._names.pop(bound, None)
            if alias.asname and alias.name in known:
                self._names[bound] = (alias.name, "")

    @classmethod
    def _scope(cls, stmts: list[ast.stmt]) -> Iterator[ast.stmt]:
        """Yield module-scope statements in order, entering blocks but not defs."""
        for stmt in stmts:
            yield stmt
            if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                continue
            for field in _COMPOUND:
                yield from cls._scope(getattr(stmt, field, []))
            for handler in getattr(stmt, "handlers", []):
                yield from cls._scope(handler.body)

    @staticmethod
    def _rebound(stmt: ast.stmt) -> list[str]:
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            return [stmt.name]
        if isinstance(stmt, ast.Assign | ast.AnnAssign | ast.AugAssign):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            return [
                n.id
                for target in targets
                for n in ast.walk(target)
                if isinstance(n, ast.Name)
            ]
        return []
