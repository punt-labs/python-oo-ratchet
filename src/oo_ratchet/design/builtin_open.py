"""Bare open calls are builtin candidates only without any module-wide binding."""

from __future__ import annotations

import ast
from typing import Self


class BuiltinOpen:
    """Use whole-module syntax rather than approximate Python's lexical scopes."""

    _tree: ast.Module

    def __new__(cls, tree: ast.Module) -> Self:
        self = super().__new__(cls)
        self._tree = tree
        return self

    def calls(self) -> list[ast.Call]:
        """Return bare open calls unless that name is bound anywhere in the tree."""
        if any(self._binds_open(node) for node in ast.walk(self._tree)):
            return []
        return [
            node
            for node in ast.walk(self._tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "open"
        ]

    @classmethod
    def _binds_open(cls, node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return node.id == "open" and isinstance(node.ctx, ast.Store)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return any(
                (alias.asname or alias.name.split(".")[0]) == "open"
                for alias in node.names
            )
        return cls._named_binding(node) == "open"

    @staticmethod
    def _named_binding(node: ast.AST) -> str | None:
        if isinstance(node, ast.arg):
            return node.arg
        if isinstance(node, ast.MatchMapping):
            return node.rest
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.ExceptHandler,
                ast.MatchAs,
                ast.MatchStar,
            ),
        ):
            return node.name
        return None
