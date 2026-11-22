"""Distinguish unqualified builtin open calls from lexically bound names."""

from __future__ import annotations

import ast
from typing import Self


class BuiltinOpen:
    """Walk lexical scopes without treating a sibling's local open as global."""

    _tree: ast.Module

    def __new__(cls, tree: ast.Module) -> Self:
        self = super().__new__(cls)
        self._tree = tree
        return self

    def calls(self) -> list[ast.Call]:
        """Return builtin open calls (not dynamic aliases or getattr)."""
        return self._scan(self._tree, (set(), set()))

    @classmethod
    def _scan(cls, node: ast.AST, scope: tuple[set[str], set[str]]) -> list[ast.Call]:
        bound, enclosing = scope
        if isinstance(
            node,
            (
                ast.Module,
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.Lambda,
            ),
        ):
            bound = enclosing | cls._bindings(node)
            if not isinstance(node, ast.ClassDef):
                enclosing = bound
        out = []
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "open" and "open" not in bound:
                out.append(node)
        for child in ast.iter_child_nodes(node):
            out.extend(cls._scan(child, (bound, enclosing)))
        return out

    @staticmethod
    def _bindings(scope: ast.AST) -> set[str]:
        bound: set[str] = set()
        pending = list(ast.iter_child_nodes(scope))
        while pending:
            node = pending.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(node.name)
                continue
            if isinstance(node, ast.Lambda):
                continue
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                bound.add(node.id)
            if isinstance(node, ast.arg):
                bound.add(node.arg)
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                bound.update(
                    alias.asname or alias.name.split(".")[0] for alias in node.names
                )
            pending.extend(ast.iter_child_nodes(node))
        return bound
