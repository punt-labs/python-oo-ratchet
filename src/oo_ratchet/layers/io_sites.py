"""The IO modules a domain module reaches, by import, literal name or open."""

from __future__ import annotations

import ast
from typing import Self

from oo_ratchet.design.domain_io import DomainIO
from oo_ratchet.design.modules import Module

from .dynamic import DynamicImports


class _IoNames:
    """The container of module names the domain-io rule treats as IO."""

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and DomainIO.is_io(name)


class IoSites:
    """Static IO imports, literal dynamic IO imports and ``builtins.open`` calls.

    ``builtins.open(...)`` is never shadowed by a local ``open`` binding, so it
    counts even where the bare-``open`` rule backs off.
    """

    _module: Module

    def __new__(cls, module: Module) -> Self:
        self = super().__new__(cls)
        self._module = module
        return self

    def names(self) -> set[str]:
        """Return the IO module names, with ``builtins.open`` for an open call."""
        dynamic = DynamicImports(self._module.tree, _IoNames())
        found = set(DomainIO(self._module).targets())
        found.update(name for _, _, name in dynamic.targets())
        if any(self._qualified_open(n) for n in ast.walk(self._module.tree)):
            found.add("builtins.open")
        return found

    @staticmethod
    def _qualified_open(node: ast.AST) -> bool:
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        return (
            isinstance(func, ast.Attribute)
            and func.attr == "open"
            and isinstance(func.value, ast.Name)
            and func.value.id == "builtins"
        )
