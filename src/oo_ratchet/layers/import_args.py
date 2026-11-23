"""Read the module name out of a dynamic-import call's literal arguments."""

from __future__ import annotations

import ast
import importlib.util


class ImportArgs:
    """The literal module name a call passes, resolved against a literal package."""

    @classmethod
    def builtin(cls, call: ast.Call) -> str | None:
        """Return the name given to ``__import__``, if it is a string literal."""
        return cls._literal(call, 0, "name")

    @classmethod
    def helper(cls, call: ast.Call) -> str | None:
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
