"""Resolve project classes through explicit declarations and import spellings."""

from __future__ import annotations

import ast
from typing import Self

from .declaration import Declaration
from .layer_imports import LayerImports
from .modules import Module, ModuleIndex
from .type_reference import TypeReference


class ProjectTypes:
    """Index class names and static import/re-export edges, never value aliases."""

    _classes: dict[str, Declaration]
    _aliases: dict[str, set[str]]
    _names: LayerImports

    def __new__(cls, index: ModuleIndex, declarations: list[Declaration]) -> Self:
        self = super().__new__(cls)
        self._names = LayerImports(index)
        self._classes = {
            f"{self._names.name(d.module)}.{d.symbol}": d
            for d in declarations
            if d.kind == "class"
        }
        self._aliases = {}
        for module in index.modules():
            self._imports(module)
        return self

    def resolve(self, module: Module, node: ast.expr | None) -> Declaration | None:
        """Resolve a direct or quoted annotation/name to a project declaration."""
        name = TypeReference.name(node)
        return self._lookup(f"{self._names.name(module)}.{name}") or self._lookup(name)

    def _lookup(self, name: str) -> Declaration | None:
        visited: set[str] = set()
        while name:
            if name in self._classes:
                return self._classes[name]
            parts = name.split(".")
            prefix = next(
                (
                    ".".join(parts[:i])
                    for i in range(len(parts), 0, -1)
                    if ".".join(parts[:i]) in self._aliases
                ),
                "",
            )
            targets = self._aliases.get(prefix, set())
            if prefix in visited or len(targets) != 1:
                return None
            visited.add(prefix)
            name = next(iter(targets)) + name[len(prefix) :]
        return None

    def _imports(self, module: Module) -> None:
        prefix = self._names.name(module)
        for node in ast.walk(module.tree):
            for bound, target in self._import_targets(module, node):
                self._aliases.setdefault(f"{prefix}.{bound}", set()).add(target)

    def _import_targets(self, module: Module, node: ast.AST) -> list[tuple[str, str]]:
        if isinstance(node, ast.Import):
            return [
                (
                    a.asname or a.name.split(".")[0],
                    a.name if a.asname else a.name.split(".")[0],
                )
                for a in node.names
            ]
        if isinstance(node, ast.ImportFrom):
            base = LayerImports._base(module, node, self._names.name(module))
            return [(a.asname or a.name, f"{base}.{a.name}") for a in node.names]
        return []
