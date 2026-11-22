"""Lexically scoped import and simple Path-value name resolution."""

from __future__ import annotations

import ast
from typing import ClassVar, Self

from .builtin_open import BuiltinOpen
from .scope_parts import ScopeParts


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
    PATH_TYPES: ClassVar[frozenset[str]] = frozenset(
        {
            "pathlib.Path",
            "pathlib.PosixPath",
            "pathlib.WindowsPath",
        }
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
        outside = environment
        header, body = ScopeParts.split(node)
        if isinstance(node, self.SCOPES):
            environment = self._environment(node, enclosing)
            if not isinstance(node, ast.ClassDef):
                enclosing = environment
        environment.update(self._imports(node))
        environment.update(dict.fromkeys(BuiltinOpen._captures(node), ""))
        self._environments[id(node)] = environment.copy()
        if isinstance(
            node,
            (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.TryStar, ast.Match),
        ):
            self._branches(node, (environment, enclosing))
        else:
            for child in header + body:
                self._visit(
                    child, scopes if child in header else (environment, enclosing)
                )
        self._assignment(node, environment)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            outside[node.name] = ""

    def _branches(
        self, node: ast.AST, scopes: tuple[dict[str, str], dict[str, str]]
    ) -> None:
        environment, enclosing = scopes
        possible = environment.copy()
        for _, value in ast.iter_fields(node):
            branch = environment.copy()
            closure = branch if enclosing is environment else enclosing.copy()
            children = value if isinstance(value, list) else [value]
            for child in children:
                if isinstance(child, ast.AST):
                    self._visit(child, (branch, closure))
            possible.update({name: alias for name, alias in branch.items() if alias})
        environment.update(possible)

    @classmethod
    def _environment(cls, scope: ast.AST, enclosing: dict[str, str]) -> dict[str, str]:
        bound = cls._parameters(scope)
        if isinstance(
            scope, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
        ):
            bound = BuiltinOpen._bindings(scope)
        return enclosing | dict.fromkeys(bound, "")

    @staticmethod
    def _parameters(scope: ast.AST) -> set[str]:
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return set()
        return {node.arg for node in ast.walk(scope.args) if isinstance(node, ast.arg)}

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
        name = cls._path_value(node.value, environment) or cls._resolve(
            node.value, environment
        )
        path = name if name in cls.PATH_TYPES else ""
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                environment[target.id] = path

    @classmethod
    def _resolve(cls, node: ast.AST, environment: dict[str, str]) -> str:
        if isinstance(node, ast.Name):
            return environment.get(node.id, "")
        if isinstance(node, ast.Attribute):
            base = cls._resolve(node.value, environment) or cls._path_value(
                node.value, environment
            )
            return f"{base}.{node.attr}"
        return ""

    @classmethod
    def _path_value(cls, node: ast.AST, environment: dict[str, str]) -> str:
        if isinstance(node, ast.Call):
            name = cls._resolve(node.func, environment)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            name = cls._path_value(node.left, environment) or cls._resolve(
                node.left, environment
            )
        else:
            return ""
        return name if name in cls.PATH_TYPES else ""
