"""Literal-string dynamic imports of modules in the scanned package."""

from __future__ import annotations

import ast
import importlib.util
from collections.abc import Container
from typing import Self

_HELPER = "import_module"
_BUILTIN = "__import__"


class DynamicImports:
    """Find ``import_module("pkg.a")`` and ``__import__("pkg.a")`` calls, anywhere.

    Deliberately over-approximate, with no binding analysis: every call in the
    module (body, function bodies, defaults, decorators, class bodies, lambdas)
    whose callee's final name or attribute is ``import_module`` or
    ``__import__`` counts, whatever object it is called on. So does a call
    through a name the module aliased to one of them (``from importlib import
    import_module as load``, ``load = importlib.import_module``), in any scope.
    The module name is the first positional argument or ``name=`` when a string
    literal; a relative name is resolved against a literal ``package``. A name
    that resolves to a module of the scanned package is an edge. A method of an
    unrelated object with that name is a false positive the author restructures.
    Computed names are out of scope.
    """

    _known: Container[str]
    _names: dict[str, str]
    _found: list[tuple[ast.Call, str, str]]

    def __new__(cls, tree: ast.Module, known: Container[str]) -> Self:
        self = super().__new__(cls)
        self._known = known
        self._names = {_HELPER: _HELPER, _BUILTIN: _BUILTIN}
        self._found = []
        nodes = list(ast.walk(tree))
        for node in nodes:
            self._learn(node)
        for node in nodes:
            if isinstance(node, ast.Call):
                self._record(node)
        return self

    def targets(self) -> list[tuple[ast.Call, str, str]]:
        """Return ``(call, name, module)`` for each recognised literal import."""
        return list(self._found)

    @staticmethod
    def _final(expr: ast.expr) -> str | None:
        if isinstance(expr, ast.Name):
            return expr.id
        return expr.attr if isinstance(expr, ast.Attribute) else None

    def _learn(self, node: ast.AST) -> None:
        """Remember names aliased to the helpers, in any scope."""
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.asname and alias.name in (_HELPER, _BUILTIN):
                    self._names[alias.asname] = alias.name
        elif isinstance(node, ast.Assign):
            kind = self._names.get(self._final(node.value) or "")
            for target in node.targets:
                if kind and isinstance(target, ast.Name):
                    self._names[target.id] = kind

    def _record(self, call: ast.Call) -> None:
        kind = self._names.get(self._final(call.func) or "")
        if kind is None:
            return
        name = self._helper(call) if kind == _HELPER else self._literal(call, 0, "name")
        if name is not None and name in self._known:
            self._found.append((call, name, name))

    @classmethod
    def _helper(cls, call: ast.Call) -> str | None:
        """Return the absolute name given to ``import_module``, if literal."""
        name = cls._literal(call, 0, "name")
        if name is None or not name.startswith("."):
            return name
        package = cls._literal(call, 1, "package")
        if package is None:
            return None
        try:
            return importlib.util.resolve_name(name, package)
        except (ImportError, ValueError):
            return None

    @staticmethod
    def _literal(call: ast.Call, index: int, keyword: str) -> str | None:
        if len(call.args) > index:
            node: ast.expr | None = call.args[index]
        else:
            node = next((k.value for k in call.keywords if k.arg == keyword), None)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None
