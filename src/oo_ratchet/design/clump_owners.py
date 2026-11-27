"""Independent class families and concrete signatures for data clumps."""

from __future__ import annotations

import ast
from typing import Self

from oo_ratchet.core.domain.declaration import Declaration
from oo_ratchet.core.domain.function_shape import FunctionShape
from oo_ratchet.core.domain.shape import ClassShape

from .data_fields import DataFields
from .data_inventory import DataInventory


class ClumpOwners:
    """Keep name sets separate while assigning methods to their lexical class."""

    _inventory: DataInventory

    def __new__(cls, inventory: DataInventory) -> Self:
        self = super().__new__(cls)
        self._inventory = inventory
        return self

    def entries(
        self,
    ) -> list[tuple[Declaration, frozenset[str], tuple[str, str]]]:
        """Return concrete declarations, their name sets and independent families."""
        declarations = self._inventory.declarations()
        classes = {
            (d.module.key, d.symbol): d for d in declarations if d.kind == "class"
        }
        entries = []
        for owner in declarations:
            parent = owner.enclosing_class(classes)
            if owner.eligible and not self._excluded(owner, parent):
                family = (owner.module.key, (parent or owner).symbol)
                entries.append((owner, self._names(owner), family))
        return entries

    @staticmethod
    def _excluded(owner: Declaration, parent: Declaration | None) -> bool:
        if isinstance(owner.node, ast.ClassDef):
            return False
        if any(ClassShape._name(d) == "overload" for d in owner.node.decorator_list):
            return True
        return (
            parent is not None
            and isinstance(parent.node, ast.ClassDef)
            and any(ClassShape._name(b) == "Protocol" for b in parent.node.bases)
        )

    @staticmethod
    def _names(owner: Declaration) -> frozenset[str]:
        if owner.kind == "class":
            return DataFields(owner).names()
        return frozenset(
            a.arg
            for a in FunctionShape(owner).parameters()
            if a.arg not in {"self", "cls"}
        )
