"""Literal-string dynamic imports of modules in the scanned package."""

from __future__ import annotations

import ast
from collections.abc import Container
from typing import Self

from .flow import BindingFlow, Bindings, Origin
from .import_args import ImportArgs

_HELPER: Origin = ("import_module", "")
_BUILTIN: Origin = ("__import__", "")
_IMPORTLIB: Origin = ("importlib", "")
_BUILTINS: Origin = ("builtins", "")
_NONE: frozenset[Origin] = frozenset()
_FROM_STDLIB = {
    ("importlib", "import_module"): _HELPER,
    ("builtins", "__import__"): _BUILTIN,
}


class DynamicImports:
    """Find ``importlib.import_module("pkg.a")`` and ``__import__("pkg.a")`` calls.

    A call counts only when its callee is bound to the stdlib helper where the
    call runs: ``importlib.import_module``, ``from importlib import
    import_module [as x]``, ``builtins.__import__``, ``from builtins import
    __import__ [as x]`` or the bare builtin. Bindings come from the same
    control flow as re-exports, per scope: a function sees its own imports and
    parameters over its enclosing scopes', and a name rebound in a scope no
    longer counts there. Relative ``from .importlib import ...`` is not the
    stdlib. The module name is read from the first positional argument or
    ``name=``; a relative name is resolved against a literal ``package``.
    Computed names are out of scope.
    """

    _known: Container[str]
    _flow: BindingFlow
    _found: list[tuple[ast.Call, str, str]]

    def __new__(cls, tree: ast.Module, known: Container[str]) -> Self:
        self = super().__new__(cls)
        self._known = known
        self._found = []
        self._flow = BindingFlow(self._bind, self._alias)
        self._visit(list(tree.body), self._flow.ever(tree.body))
        return self

    def targets(self) -> list[tuple[ast.Call, str, str]]:
        """Return ``(call, name, module)`` for each recognised literal import."""
        return list(self._found)

    @classmethod
    def _bind(cls, stmt: ast.Import | ast.ImportFrom) -> Bindings:
        if isinstance(stmt, ast.ImportFrom):
            module = stmt.module if stmt.level == 0 else None
            return {
                (a.asname or a.name): cls._from_stdlib(module or "", a.name)
                for a in stmt.names
            }
        return {
            (a.asname or a.name.split(".")[0]): cls._module_kind(a) for a in stmt.names
        }

    @classmethod
    def _alias(cls, stmt: ast.stmt, state: Bindings) -> Bindings | None:
        """Bind ``name = <stdlib helper>`` to the helper; None for anything else."""
        if not isinstance(stmt, ast.Assign):
            return None
        if not isinstance(stmt.value, ast.Name | ast.Attribute):
            return None
        kinds = cls._callee(stmt.value, state)
        names = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
        return {name: kinds for name in names} if kinds else None

    @staticmethod
    def _from_stdlib(module: str, name: str) -> frozenset[Origin]:
        kind = _FROM_STDLIB.get((module, name))
        return frozenset({kind}) if kind else _NONE

    @staticmethod
    def _module_kind(alias: ast.alias) -> frozenset[Origin]:
        if alias.name == "importlib" or (
            alias.asname is None and alias.name.startswith("importlib.")
        ):
            return frozenset({_IMPORTLIB})
        return frozenset({_BUILTINS}) if alias.name == "builtins" else _NONE

    def _visit(self, nodes: list[ast.AST], env: Bindings) -> None:
        stack = nodes
        while stack:
            node = stack.pop()
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                self._function(node, env)
                continue
            if isinstance(node, ast.Call):
                self._record(node, env)
            stack.extend(ast.iter_child_nodes(node))

    def _function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, env: Bindings
    ) -> None:
        params = {a.arg: _NONE for a in ast.walk(node.args) if isinstance(a, ast.arg)}
        local = self._flow.ever(node.body)
        self._visit(list(node.body), {**env, **params, **local})

    def _record(self, call: ast.Call, env: Bindings) -> None:
        kinds = self._callee(call.func, env)
        if _HELPER in kinds:
            name = ImportArgs.helper(call)
        elif _BUILTIN in kinds:
            name = ImportArgs.builtin(call)
        else:
            return
        if name is not None and name in self._known:
            self._found.append((call, name, name))

    @staticmethod
    def _callee(func: ast.expr, env: Bindings) -> frozenset[Origin]:
        if isinstance(func, ast.Name):
            bare = frozenset({_BUILTIN}) if func.id == "__import__" else _NONE
            return env.get(func.id, bare)
        if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)):
            return _NONE
        owner = env.get(func.value.id, _NONE)
        if func.attr == "import_module" and _IMPORTLIB in owner:
            return frozenset({_HELPER})
        if func.attr == "__import__" and _BUILTINS in owner:
            return frozenset({_BUILTIN})
        return _NONE
