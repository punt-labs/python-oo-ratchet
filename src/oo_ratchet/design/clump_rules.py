"""Repeated syntactic class fields and function parameter bundles."""

from __future__ import annotations

from typing import Self

from .clump_sets import ClumpSets
from .data_fields import DataFields
from .data_inventory import DataInventory
from .declaration import Declaration
from .findings import Finding, Rules
from .function_shape import FunctionShape


class ClumpRules:
    """Report each owner of a maximal shared name set, with no type inference."""

    _inventory: DataInventory

    def __new__(cls, inventory: DataInventory) -> Self:
        self = super().__new__(cls)
        self._inventory = inventory
        return self

    def findings(self) -> list[Finding]:
        """Attach sorted shared names to each of their eligible owners."""
        owners = [
            d for d in self._inventory.declarations() if self._inventory.eligible(d)
        ]
        sets = [self._names(d) for d in owners]
        return [
            owners[i].finding(Rules.DATA_CLUMP, ", ".join(sorted(names)))
            for names, support in ClumpSets(sets).repeated()
            for i in support
        ]

    @staticmethod
    def _names(owner: Declaration) -> frozenset[str]:
        if owner.kind == "class":
            return DataFields(owner).names()
        return frozenset(
            a.arg
            for a in FunctionShape(owner).parameters()
            if a.arg not in {"self", "cls"}
        )
