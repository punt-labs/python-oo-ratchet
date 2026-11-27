"""Resolve an import statement to the in-tree module it names."""

from __future__ import annotations

import ast
from typing import Self

from .modules import Module, ModuleIndex


class ImportTargets:
    """Map ``from X import ...`` nodes to module keys of the scanned package.

    Absolute imports must start with the package name; relative imports climb
    from the importing module's own package. Anything that does not land on a
    parsed module (external libraries, ``from pkg import submodule``) is
    ``None``.
    """

    _index: ModuleIndex
    _pkg_name: str

    def __new__(cls, index: ModuleIndex) -> Self:
        self = super().__new__(cls)
        self._index = index
        self._pkg_name = index.package_name
        return self

    def key_for(self, module: Module, node: ast.ImportFrom) -> str | None:
        """Return the key of the module ``node`` imports from, if in the tree."""
        inner = (
            self._absolute(node) if node.level == 0 else self._relative(module, node)
        )
        if inner is None:
            return None
        key = ".".join(inner) or "__init__"
        return key if self._index.get(key) is not None else None

    def _absolute(self, node: ast.ImportFrom) -> list[str] | None:
        parts = (node.module or "").split(".")
        return parts[1:] if parts[0] == self._pkg_name else None

    @staticmethod
    def _relative(module: Module, node: ast.ImportFrom) -> list[str] | None:
        base = module.package_parts()
        climb = node.level - 1
        if climb > len(base):
            return None
        tail = node.module.split(".") if node.module else []
        return base[: len(base) - climb] + tail

    @staticmethod
    def type_only(tree: ast.Module) -> set[int]:
        """Return ids of every node under an ``if TYPE_CHECKING:`` block."""
        nodes: set[int] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            test = node.test
            named = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
                isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
            )
            if named:
                nodes.update(id(n) for stmt in node.body for n in ast.walk(stmt))
        return nodes
