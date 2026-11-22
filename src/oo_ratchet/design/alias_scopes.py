"""Lexically scoped import and simple Path-value name resolution."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from typing import ClassVar, Self

from .builtin_open import BuiltinOpen


class AliasScopes:
    """Keep local bindings from resolving as an unrelated outer import."""

    SCOPES: ClassVar[tuple[type[ast.AST], ...]] = (
        ast.Module,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.Lambda,
        ast.ListComp,
        ast.SetComp,
        ast.DictComp,
        ast.GeneratorExp,
    )
    _environments: dict[int, dict[str, str]]

    def __new__(cls, tree: ast.Module) -> Self:
        self = super().__new__(cls)
        self._environments = {}
        self._visit(tree, ({}, {}))
        return self

    def name(self, node: ast.AST) -> str:
        """Resolve an expression using its lexical import bindings."""
        return self._resolve(node, self._environments.get(id(node), {}))

    def _visit(
        self, node: ast.AST, scopes: tuple[dict[str, str], dict[str, str]]
    ) -> None:
        environment, enclosing = scopes
        if isinstance(node, self.SCOPES):
            environment = self._environment(node, enclosing)
            if not isinstance(node, ast.ClassDef):
                enclosing = environment
        self._environments[id(node)] = environment
        for child in ast.iter_child_nodes(node):
            self._visit(child, (environment, enclosing))

    @classmethod
    def _environment(cls, scope: ast.AST, enclosing: dict[str, str]) -> dict[str, str]:
        environment = enclosing | dict.fromkeys(BuiltinOpen._bindings(scope), "")
        for node in cls._own(scope):
            environment.update(cls._imports(node))
        for node in cls._own(scope):
            cls._assignment(node, environment)
        return environment

    @classmethod
    def _own(cls, scope: ast.AST) -> Iterator[ast.AST]:
        pending = list(reversed(list(ast.iter_child_nodes(scope))))
        while pending:
            node = pending.pop()
            yield node
            if not isinstance(node, cls.SCOPES):
                pending.extend(reversed(list(ast.iter_child_nodes(node))))

    @staticmethod
    def _imports(node: ast.AST) -> dict[str, str]:
        if isinstance(node, ast.Import):
            return {
                alias.asname or alias.name.split(".")[0]: alias.name
                if alias.asname
                else alias.name.split(".")[0]
                for alias in node.names
            }
        if isinstance(node, ast.ImportFrom) and node.level == 0:
            return {
                alias.asname or alias.name: f"{node.module}.{alias.name}"
                for alias in node.names
            }
        return {}

    @classmethod
    def _assignment(cls, node: ast.AST, environment: dict[str, str]) -> None:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            return
        name = cls._resolve(node.value, environment)
        path = (
            name
            if name in {"pathlib.Path", "pathlib.PosixPath", "pathlib.WindowsPath"}
            else ""
        )
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                environment[target.id] = path

    @classmethod
    def _resolve(cls, node: ast.AST, environment: dict[str, str]) -> str:
        if isinstance(node, ast.Name):
            return environment.get(node.id, "")
        if isinstance(node, ast.Attribute):
            return f"{cls._resolve(node.value, environment)}.{node.attr}"
        if isinstance(node, ast.Call):
            return cls._resolve(node.func, environment)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return cls._resolve(node.left, environment)
        return ""
