"""Literal-string dynamic imports of modules in the scanned package."""

from __future__ import annotations

import ast
import importlib.util
from collections.abc import Container
from typing import Self


class DynamicImports:
    """Find ``importlib.import_module("pkg.a")`` and ``__import__("pkg.a")`` calls.

    A call counts only when ``import_module`` is bound to ``importlib`` in this
    module -- ``importlib.import_module``, ``from importlib import import_module
    [as x]`` or an alias of ``importlib`` -- so a method of some other object
    with that name is not an import. The module name is read from the first
    positional argument or ``name=``; a relative name is resolved against a
    literal ``package`` argument. Computed names are out of scope.
    """

    _tree: ast.Module
    _known: Container[str]
    _importlib: set[str]
    _helpers: set[str]

    def __new__(cls, tree: ast.Module, known: Container[str]) -> Self:
        self = super().__new__(cls)
        self._tree = tree
        self._known = known
        self._importlib = set()
        self._helpers = set()
        for node in ast.walk(tree):
            self._learn(node)
        return self

    def targets(self) -> list[tuple[ast.Call, str, str]]:
        """Return ``(call, name, module)`` for each recognised literal import."""
        found: list[tuple[ast.Call, str, str]] = []
        for node in ast.walk(self._tree):
            if isinstance(node, ast.Call):
                module = self._module(node)
                if module is not None and module in self._known:
                    found.append((node, module, module))
        return found

    def _learn(self, node: ast.AST) -> None:
        if isinstance(node, ast.Import):
            self._learn_import(node)
        elif isinstance(node, ast.ImportFrom) and node.module == "importlib":
            self._helpers.update(
                a.asname or a.name for a in node.names if a.name == "import_module"
            )

    def _learn_import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "importlib":
                self._importlib.add(alias.asname or "importlib")
            elif alias.asname is None and alias.name.startswith("importlib."):
                self._importlib.add("importlib")

    def _module(self, call: ast.Call) -> str | None:
        func = call.func
        if isinstance(func, ast.Name) and func.id == "__import__":
            return self._literal(call, 0, "name")
        if not self._is_import_module(func):
            return None
        return self._resolve(
            self._literal(call, 0, "name"), self._literal(call, 1, "package")
        )

    @staticmethod
    def _resolve(name: str | None, package: str | None) -> str | None:
        if name is None or not name.startswith("."):
            return name
        if package is None:
            return None
        try:
            return importlib.util.resolve_name(name, package)
        except (ImportError, ValueError):
            return None

    def _is_import_module(self, func: ast.expr) -> bool:
        if isinstance(func, ast.Name):
            return func.id in self._helpers
        return (
            isinstance(func, ast.Attribute)
            and func.attr == "import_module"
            and isinstance(func.value, ast.Name)
            and func.value.id in self._importlib
        )

    @staticmethod
    def _literal(call: ast.Call, index: int, keyword: str) -> str | None:
        if len(call.args) > index:
            node: ast.expr | None = call.args[index]
        else:
            node = next((k.value for k in call.keywords if k.arg == keyword), None)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None
