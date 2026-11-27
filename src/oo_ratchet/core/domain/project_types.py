"""Resolve project classes through explicit declarations and import spellings."""

from __future__ import annotations

import ast
from collections import Counter
from typing import Self

from .declaration import Declaration
from .layer_imports import LayerImports
from .modules import Module, ModuleIndex
from .receiver_bindings import ReceiverBindings
from .type_reference import type_name


class ProjectTypes:
    """Index class names and static import/re-export edges, never value aliases."""

    _classes: dict[str, Declaration]
    _aliases: dict[str, set[str]]
    _names: LayerImports
    _ambiguous: set[str]

    def __new__(cls, index: ModuleIndex, declarations: list[Declaration]) -> Self:
        self = super().__new__(cls)
        self._names = LayerImports(index)
        self._classes = {
            f"{self._names.name(d.module)}.{d.symbol}": d
            for d in declarations
            if d.kind == "class"
        }
        self._aliases = {}
        self._ambiguous = set()
        for module in index.modules():
            self._imports(module)
        return self

    def resolve(self, module: Module, node: ast.expr | None) -> Declaration | None:
        """Resolve a direct or quoted annotation/name to a project declaration."""
        name = type_name(node)
        local = f"{self._names.name(module)}.{name}"
        if self._is_ambiguous(local):
            return None
        return self._lookup(local) or self._lookup(name)

    def _is_ambiguous(self, name: str) -> bool:
        parts = name.split(".")
        return any(
            ".".join(parts[:i]) in self._ambiguous for i in range(1, len(parts) + 1)
        )

    def _lookup(self, name: str) -> Declaration | None:
        visited: set[str] = set()
        while name:
            if self._is_ambiguous(name):
                return None
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
        nodes = self._module_nodes(module.tree)
        counts = Counter(name for n in nodes for name in ReceiverBindings._names(n))
        self._ambiguous.update(
            f"{prefix}.{name}" for name, count in counts.items() if count > 1
        )
        for node in nodes:
            for bound, target in self._import_targets(module, node):
                self._aliases.setdefault(f"{prefix}.{bound}", set()).add(target)

    @staticmethod
    def _module_nodes(tree: ast.Module) -> list[ast.AST]:
        pending: list[ast.AST] = list(reversed(tree.body))
        out: list[ast.AST] = []
        while pending:
            node = pending.pop()
            out.append(node)
            pending.extend(reversed(ReceiverBindings._children(node)))
        return out

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
            base = self._names.base(module, node)
            return [(a.asname or a.name, f"{base}.{a.name}") for a in node.names]
        return []
