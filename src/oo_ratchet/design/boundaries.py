"""Find concrete classes imported across top-level package boundaries."""

from __future__ import annotations

import ast
from typing import Self

from .findings import Finding, Rules
from .modules import Module, ModuleIndex
from .targets import ImportTargets


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
        resolved = self._resolve(key, name, hops=1)
        if resolved is None:
            return False
        shape = resolved.classes[name]
        return not (shape.is_exempt or shape.is_abstract)

    def _resolve(self, key: str, name: str, hops: int) -> Module | None:
        module = self._index.get(key)
        if module is None:
            return None
        if name in module.classes:
            return module
        if not module.is_package or hops == 0:
            return None
        node = self._reexport(module, name)
        inner = None if node is None else self._targets.key_for(module, node)
        return None if inner is None else self._resolve(inner, name, hops - 1)

    @staticmethod
    def _reexport(module: Module, name: str) -> ast.ImportFrom | None:
        """Return the ``from X import name`` in a package ``__init__``."""
        for node in module.tree.body:
            if isinstance(node, ast.ImportFrom) and any(
                a.name == name and a.asname in {None, name} for a in node.names
            ):
                return node
        return None
