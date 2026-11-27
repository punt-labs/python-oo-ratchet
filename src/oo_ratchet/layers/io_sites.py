"""The IO modules a domain module reaches, by import, literal name or open."""

from __future__ import annotations

import ast
from typing import Self

from oo_ratchet.core.domain.domain_io import DomainIO
from oo_ratchet.core.domain.modules import Module
from oo_ratchet.core.domain.targets import ImportTargets

from .dynamic import DynamicImports

OPEN = "builtins.open"


class _IoNames:
    """The module names the domain-io rule treats as IO, outside ``package``."""

    _package: str

    def __new__(cls, package: str) -> Self:
        self = super().__new__(cls)
        self._package = package
        return self

    def __contains__(self, name: object) -> bool:
        return (
            isinstance(name, str)
            and DomainIO.is_io(name)
            and name != self._package
            and not name.startswith(self._package + ".")
        )


class IoSites:
    """Static IO imports, literal dynamic IO imports and builtin ``open`` uses.

    Names inside the scanned package are never IO, whatever the package is
    called. Anything under ``if TYPE_CHECKING:`` does not count. ``builtins.open``
    is an edge when called through ``builtins`` or an alias of it, or imported
    with ``from builtins import open``; a local ``open`` binding cannot shadow it.
    """

    _module: Module
    _io: _IoNames
    _type_only: set[int]

    def __new__(cls, module: Module, package: str) -> Self:
        self = super().__new__(cls)
        self._module = module
        self._io = _IoNames(package)
        self._type_only = ImportTargets.type_only(module.tree)
        return self

    def names(self) -> set[str]:
        """Return the IO module names, with ``builtins.open`` for an open use."""
        static = DomainIO(self._module).targets()
        found = {name for name in static if name == OPEN or name in self._io}
        dynamic = DynamicImports(self._module.tree, self._io).targets()
        found.update(n for call, _, n in dynamic if id(call) not in self._type_only)
        if self._opens():
            found.add(OPEN)
        return found

    def _opens(self) -> bool:
        aliases = self._aliases()
        return any(
            id(n) not in self._type_only
            and (self._from_open(n) or self._qualified_open(n, aliases))
            for n in ast.walk(self._module.tree)
        )

    def _aliases(self) -> set[str]:
        """Return the names a runtime ``import builtins [as b]`` binds."""
        return {"builtins"} | {
            a.asname or a.name
            for n in ast.walk(self._module.tree)
            if isinstance(n, ast.Import) and id(n) not in self._type_only
            for a in n.names
            if a.name == "builtins"
        }

    @staticmethod
    def _from_open(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.ImportFrom)
            and node.module == "builtins"
            and not node.level
            and any(a.name == "open" for a in node.names)
        )

    @staticmethod
    def _qualified_open(node: ast.AST, aliases: set[str]) -> bool:
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        return (
            isinstance(func, ast.Attribute)
            and func.attr == "open"
            and isinstance(func.value, ast.Name)
            and func.value.id in aliases
        )
