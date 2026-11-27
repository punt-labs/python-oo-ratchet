"""Advisory Tier 0 ceilings using existing code-line and complexity measures."""

from __future__ import annotations

import ast
from typing import ClassVar, Self

from oo_ratchet.core.domain.declaration import Declaration
from oo_ratchet.core.domain.findings import Finding, Rules
from oo_ratchet.core.domain.modules import Module, ModuleIndex
from oo_ratchet.core.domain.shape import ClassShape
from oo_ratchet.oo.code_lines import CodeLines
from oo_ratchet.oo.metrics import ModuleMetrics

from .data_inventory import DataInventory
from .signature_rules import SignatureRules


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
            module.finding(Rules.SIZE_CAP, 1, "<module>", f"module_size={count} > 400")
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
            "params": cls._parameters(owner),
            "complexity": ModuleMetrics._cyclomatic_complexity(owner.node),
        }

    @staticmethod
    def _parameters(owner: Declaration) -> int:
        if isinstance(owner.node, ast.ClassDef):
            return 0
        args = owner.node.args
        count = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
        return count - (SignatureRules._receiver(owner) is not None)
