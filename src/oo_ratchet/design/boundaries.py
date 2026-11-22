"""Find concrete classes imported across top-level package boundaries."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, Self

from .findings import Finding, Rules
from .modules import Module, ModuleIndex
from .targets import ImportTargets

if TYPE_CHECKING:
    from .shape import ClassShape


class BoundaryCheck:
    """Flag ``from <other package> import <ConcreteClass>`` imports.

    A boundary is a top-level sub-package (``voxd``, ``providers``); root-level
    modules form one more component. The imported name must resolve, directly
    or through one ``__init__`` re-export, to a class defined in the tree that
    is neither a value shape nor an interface. Imports under
    ``if TYPE_CHECKING:`` are still reported, marked type-only.
    """

    _index: ModuleIndex
    _targets: ImportTargets

    def __new__(cls, index: ModuleIndex) -> Self:
        self = super().__new__(cls)
        self._index = index
        self._targets = ImportTargets(index)
        return self

    def findings(self) -> list[Finding]:
        """Return every concrete cross-package import in the tree."""
        return [f for module in self._index.modules() for f in self._scan(module)]

    def _scan(self, module: Module) -> list[Finding]:
        type_only = self._targets.type_only(module.tree)
        out: list[Finding] = []
        imports = (n for n in ast.walk(module.tree) if isinstance(n, ast.ImportFrom))
        for node in imports:
            target = self._crossing(module, node)
            if target is None:
                continue
            out.extend(
                self._finding(
                    module, node, alias.name, target, typed=id(node) in type_only
                )
                for alias in node.names
                if self._is_concrete(target, alias.name)
            )
        return out

    def _crossing(self, module: Module, node: ast.ImportFrom) -> str | None:
        """Return the target key when ``node`` imports from another package."""
        target = self._targets.key_for(module, node)
        if target is None:
            return None
        same = self._index.component(target) == self._index.component(module.key)
        return None if same else target

    def _finding(
        self,
        module: Module,
        node: ast.ImportFrom,
        name: str,
        target: str,
        *,
        typed: bool,
    ) -> Finding:
        source = self._index.component(target) or "<root>"
        suffix = " (type-only)" if typed else ""
        return Finding(
            Rules.CONCRETE_IMPORT,
            str(module.path),
            node.lineno,
            name,
            f"imports concrete {name} from {source} ({target}){suffix}",
        )

    def _is_concrete(self, key: str, name: str) -> bool:
        shape = self._resolve(key, name, hops=1)
        if shape is None:
            return False
        return not (shape.is_exempt or shape.is_abstract or shape.is_value_wrapper)

    def _resolve(self, key: str, name: str, hops: int) -> ClassShape | None:
        module = self._index.get(key)
        if module is None:
            return None
        if name in module.classes:
            return module.classes[name]
        if not module.is_package or hops == 0:
            return None
        found = self._reexport(module, name)
        if found is None:
            return None
        node, source = found
        inner = self._targets.key_for(module, node)
        return None if inner is None else self._resolve(inner, source, hops - 1)

    @staticmethod
    def _reexport(module: Module, name: str) -> tuple[ast.ImportFrom, str] | None:
        """Return the import in a package ``__init__`` exporting ``name``.

        Also returns the name the class has in its source module, which
        differs from ``name`` for ``from .core import Engine as PublicEngine``.
        """
        for node in module.tree.body:
            if not isinstance(node, ast.ImportFrom):
                continue
            for alias in node.names:
                if (alias.asname or alias.name) == name:
                    return node, alias.name
        return None
