"""Unambiguous module-level imports of the standard Protocol markers."""

from __future__ import annotations

import ast
from collections import Counter
from typing import Self

from .modules import Module
from .project_types import ProjectTypes
from .receiver_bindings import ReceiverBindings


class ProtocolImports:
    """Match import spellings, never evaluate assignments or local scopes."""

    _module: Module

    def __new__(cls, module: Module) -> Self:
        self = super().__new__(cls)
        self._module = module
        return self

    def names(self) -> set[str]:
        """Return direct and module-qualified markers with a single root binding."""
        nodes = ProjectTypes._module_nodes(self._module.tree)
        counts = Counter(name for n in nodes for name in ReceiverBindings._names(n))
        return {
            reference
            for n in nodes
            for bound, reference in self._imports(n)
            if counts[bound] == 1
        }

    @classmethod
    def _imports(cls, node: ast.AST) -> list[tuple[str, str]]:
        if isinstance(node, ast.Import):
            return cls._modules(node)
        return cls._members(node)

    @staticmethod
    def _modules(node: ast.Import) -> list[tuple[str, str]]:
        return [
            (a.asname or a.name, f"{a.asname or a.name}.Protocol")
            for a in node.names
            if a.name in {"typing", "typing_extensions"}
        ]

    @staticmethod
    def _members(node: ast.AST) -> list[tuple[str, str]]:
        if (
            not isinstance(node, ast.ImportFrom)
            or node.level
            or node.module not in {"typing", "typing_extensions"}
        ):
            return []
        return [
            (a.asname or a.name, a.asname or a.name)
            for a in node.names
            if a.name == "Protocol"
        ]
