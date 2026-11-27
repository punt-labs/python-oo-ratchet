"""Independent class families and concrete signatures for data clumps."""

from __future__ import annotations

import ast
from typing import Self

from oo_ratchet.core.domain.declaration import Declaration
from oo_ratchet.core.domain.function_shape import FunctionShape
from oo_ratchet.core.domain.shape import ClassShape

from .data_fields import DataFields
from .data_inventory import DataInventory
from .eligible_modules import EligibleModules


class ClumpOwners:
    """Keep name sets separate while assigning methods to their lexical class."""

    _inventory: DataInventory
    _eligible: EligibleModules

    def __new__(cls, inventory: DataInventory, eligible: EligibleModules) -> Self:
        self = super().__new__(cls)
        self._inventory = inventory
        self._eligible = eligible
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
            parent = self._parent(owner, classes)
            if self._eligible.holds(owner) and not self._excluded(owner, parent):
                family = (owner.module.key, (parent or owner).symbol)
                entries.append((owner, self._names(owner), family))
        return entries

    @staticmethod
    def _parent(
        owner: Declaration, classes: dict[tuple[str, str], Declaration]
    ) -> Declaration | None:
        if owner.kind == "class":
            return None
        prefix = owner.symbol.rpartition(".")[0]
        while prefix:
            parent = classes.get((owner.module.key, prefix))
            if parent is not None:
                return parent
            prefix = prefix.rpartition(".")[0]
        return None

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
