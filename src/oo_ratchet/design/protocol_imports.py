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
        """Return aliases bound once by a top-level Protocol import."""
        nodes = ProjectTypes._module_nodes(self._module.tree)
        counts = Counter(name for n in nodes for name in ReceiverBindings._names(n))
        return {name for n in nodes for name in self._imports(n) if counts[name] == 1}

    @staticmethod
    def _imports(node: ast.AST) -> list[str]:
        if (
            not isinstance(node, ast.ImportFrom)
            or node.level
            or node.module not in {"typing", "typing_extensions"}
        ):
            return []
        return [a.asname or a.name for a in node.names if a.name == "Protocol"]
