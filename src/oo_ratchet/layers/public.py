"""The public names of a module, as ``from module import *`` would bind them."""

from __future__ import annotations

import ast

from .flow import BindingFlow


class PublicNames:
    """Read a module's ``__all__`` if it is a literal, else its public bindings."""

    @classmethod
    def of(cls, tree: ast.Module) -> list[str]:
        """Return the names a wildcard import of this module would bind."""
        listed = cls._all(tree)
        if listed is not None:
            return listed
        return sorted(n for n in cls._bound(tree.body) if not n.startswith("_"))

    @classmethod
    def _all(cls, tree: ast.Module) -> list[str] | None:
        found: list[str] | None = None
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign) and cls._assigns_all(stmt):
                found = cls._strings(stmt.value)
        return found

    @staticmethod
    def _assigns_all(stmt: ast.Assign) -> bool:
        return any(isinstance(t, ast.Name) and t.id == "__all__" for t in stmt.targets)

    @staticmethod
    def _strings(value: ast.expr) -> list[str]:
        if not isinstance(value, ast.List | ast.Tuple):
            return []
        return [
            e.value
            for e in value.elts
            if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]

    @classmethod
    def _bound(cls, body: list[ast.stmt]) -> set[str]:
        names: set[str] = set()
        stack = list(body)
        while stack:
            stmt = stack.pop()
            names.update(BindingFlow.rebound(stmt))
            if isinstance(stmt, ast.Import | ast.ImportFrom):
                names.update(cls._imported(stmt))
            else:
                stack.extend(cls._children(stmt))
        return names

    @staticmethod
    def _imported(stmt: ast.Import | ast.ImportFrom) -> list[str]:
        return [
            alias.asname or alias.name.split(".")[0]
            for alias in stmt.names
            if alias.name != "*"
        ]

    @staticmethod
    def _children(stmt: ast.stmt) -> list[ast.stmt]:
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            return []
        found: list[ast.stmt] = []
        for node in ast.iter_child_nodes(stmt):
            if isinstance(node, ast.stmt):
                found.append(node)
            elif isinstance(node, ast.ExceptHandler | ast.match_case):
                found.extend(node.body)
        return found
