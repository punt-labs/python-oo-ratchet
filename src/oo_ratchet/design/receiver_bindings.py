"""Syntactic binding counts, independent of ordering or control flow."""

from __future__ import annotations

import ast
from collections import Counter
from typing import Self

from .declaration import Declaration
from .function_shape import FunctionShape


class ReceiverBindings:
    """Count local bindings and declarations without entering nested bodies."""

    _owner: Declaration

    def __new__(cls, owner: Declaration) -> Self:
        self = super().__new__(cls)
        self._owner = owner
        return self

    def counts(self) -> Counter[str]:
        """Count parameters, writes, captures, declarations and deletions alike."""
        writes = Counter(a.arg for a in FunctionShape(self._owner).parameters())
        for node in self._nodes():
            writes.update(self._names(node))
        return writes

    def _nodes(self) -> list[ast.AST]:
        pending: list[ast.AST] = list(reversed(self._owner.node.body))
        out: list[ast.AST] = []
        while pending:
            node = pending.pop()
            out.append(node)
            pending.extend(reversed(self._children(node)))
        return out

    @classmethod
    def _children(cls, node: ast.AST) -> list[ast.AST]:
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
        ):
            return [
                child
                for field, value in ast.iter_fields(node)
                if field != "body"
                for child in cls._values(value)
            ]
        return list(ast.iter_child_nodes(node))

    @staticmethod
    def _values(value: object) -> list[ast.AST]:
        if isinstance(value, ast.AST):
            return [value]
        if isinstance(value, list):
            return [node for node in value if isinstance(node, ast.AST)]
        return []

    @classmethod
    def _names(cls, node: ast.AST) -> list[str]:
        if isinstance(node, ast.Name):
            return [node.id] if isinstance(node.ctx, (ast.Store, ast.Del)) else []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return [node.name]
        if isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)):
            return [node.name] if node.name else []
        if isinstance(node, ast.MatchMapping):
            return [node.rest] if node.rest else []
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            return node.names
        return cls._imports(node)

    @staticmethod
    def _imports(node: ast.AST) -> list[str]:
        if isinstance(node, ast.Import):
            return [a.asname or a.name.split(".")[0] for a in node.names]
        if isinstance(node, ast.ImportFrom):
            return [a.asname or a.name for a in node.names]
        return []
