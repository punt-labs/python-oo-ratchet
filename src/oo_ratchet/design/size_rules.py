"""Advisory Tier 0 ceilings using existing code-line and complexity measures."""

from __future__ import annotations

import ast
from typing import ClassVar, Self

from oo_ratchet.oo.code_lines import CodeLines
from oo_ratchet.oo.metrics import ModuleMetrics

from .data_inventory import DataInventory
from .declaration import Declaration
from .findings import Finding, Rules
from .modules import Module, ModuleIndex
from .shape import ClassShape, Method


class SizeRules:
    """Aggregate exceeded measures per symbol rather than duplicating its key."""

    _CAPS: ClassVar[dict[str, int]] = {"methods": 25, "params": 5, "complexity": 10}
    _index: ModuleIndex
    _inventory: DataInventory

    def __new__(cls, index: ModuleIndex, inventory: DataInventory) -> Self:
        self = super().__new__(cls)
        self._index = index
        self._inventory = inventory
        return self

    def findings(self) -> list[Finding]:
        """Check modules, classes and signatures regardless of layer."""
        return [f for m in self._index.modules() for f in self._module(m)] + [
            f for d in self._inventory.declarations() for f in self._declaration(d)
        ]

    @staticmethod
    def _module(module: Module) -> list[Finding]:
        try:
            count = CodeLines(
                module.path.read_text(encoding="utf-8"), module.tree
            ).count
        except (OSError, UnicodeError):
            return []
        if count <= 400:
            return []
        return [
            Finding(
                Rules.SIZE_CAP,
                str(module.path),
                1,
                "<module>",
                f"module_size={count} > 400",
            )
        ]

    @classmethod
    def _declaration(cls, owner: Declaration) -> list[Finding]:
        measures = cls._measures(owner)
        details = [
            f"{name}={value} > {cls._CAPS[name]}"
            for name, value in measures.items()
            if value > cls._CAPS[name]
        ]
        return [owner.finding(Rules.SIZE_CAP, "; ".join(details))] if details else []

    @classmethod
    def _measures(cls, owner: Declaration) -> dict[str, int]:
        if isinstance(owner.node, ast.ClassDef):
            return {"methods": len(ClassShape(owner.node).method_names())}
        return {
            "params": cls._parameters(owner.node),
            "complexity": ModuleMetrics._cyclomatic_complexity(owner.node),
        }

    @staticmethod
    def _parameters(node: Method) -> int:
        args = node.args
        positional = args.posonlyargs + args.args
        count = len(positional) + len(args.kwonlyargs)
        if positional and positional[0].arg in {"self", "cls"}:
            count -= 1
        return count
