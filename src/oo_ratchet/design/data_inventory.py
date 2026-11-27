"""Inventory syntactic declarations, independently of receiver typing."""

from __future__ import annotations

import ast
from typing import Self

from oo_ratchet.core.domain.declaration import Declaration
from oo_ratchet.core.domain.layer_config import LayerConfig
from oo_ratchet.core.domain.layer_imports import LayerImports
from oo_ratchet.core.domain.modules import Module, ModuleIndex


class DataInventory:
    """Keep all project declarations, each marked eligible or not for data rules."""

    _declarations: list[Declaration]
    _eligible: frozenset[str]

    def __new__(cls, index: ModuleIndex, config: LayerConfig | None) -> Self:
        self = super().__new__(cls)
        self._declarations = []
        names = LayerImports(index)
        self._eligible = frozenset(
            m.key
            for m in index.modules()
            if config is None
            or config.layer(names.canonical_name(m)) not in {"entry", "adapters"}
        )
        for module in index.modules():
            self._walk(module, module.tree, ("", "module"))
        return self

    def declarations(self) -> list[Declaration]:
        """Return classes and functions in source order, including nested defs."""
        return list(self._declarations)

    def _walk(self, module: Module, node: ast.AST, context: tuple[str, str]) -> None:
        prefix, parent = context
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = (
                "class"
                if isinstance(node, ast.ClassDef)
                else {
                    "module": "function",
                    "class": "method",
                }.get(parent, "nested")
            )
            symbol = prefix + node.name
            self._declarations.append(
                Declaration(
                    module, node, symbol, kind, eligible=module.key in self._eligible
                )
            )
            context = (symbol + ".", "class" if kind == "class" else "function-body")
        for child in ast.iter_child_nodes(node):
            self._walk(module, child, context)
