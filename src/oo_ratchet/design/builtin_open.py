"""Distinguish unqualified builtin open calls from lexically bound names."""

from __future__ import annotations

import ast
from typing import Self

from .scope_parts import ScopeParts


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
        header, body = ScopeParts.split(node)
        if isinstance(
            node,
            (
                ast.Module,
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.Lambda,
                ast.ListComp,
                ast.SetComp,
                ast.DictComp,
                ast.GeneratorExp,
            ),
        ):
            bound = enclosing | cls._bindings(node)
            if not isinstance(node, ast.ClassDef):
                enclosing = bound
        out = []
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "open" and "open" not in bound:
                out.append(node)
        for child in header + body:
            out.extend(
                cls._scan(child, scope if child in header else (bound, enclosing))
            )
        return out

    @classmethod
    def _bindings(cls, scope: ast.AST) -> set[str]:
        bound: set[str] = set()
        pending = list(ast.iter_child_nodes(scope))
        while pending:
            node = pending.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(node.name)
                continue
            if isinstance(
                node,
                (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp),
            ):
                continue
            bound.update(cls._direct_binding(node))
            bound.update(cls._captures(node))
            pending.extend(ast.iter_child_nodes(node))
        return bound

    @staticmethod
    def _direct_binding(node: ast.AST) -> set[str]:
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            return {node.id}
        if isinstance(node, ast.arg):
            return {node.arg}
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return {alias.asname or alias.name.split(".")[0] for alias in node.names}
        return set()

    @staticmethod
    def _captures(node: ast.AST) -> set[str]:
        if isinstance(node, (ast.MatchAs, ast.MatchStar)):
            return {node.name} if node.name else set()
        if isinstance(node, ast.MatchMapping):
            return {node.rest} if node.rest else set()
        return set()
