"""Repeated syntactic class fields and function parameter bundles."""

from __future__ import annotations

from typing import Self

from oo_ratchet.core.domain.findings import Finding, Rules

from .clump_owners import ClumpOwners
from .clump_sets import ClumpSets
from .data_inventory import DataInventory
from .eligible_modules import EligibleModules


class ClumpRules:
    """Report each owner of a maximal shared name set, with no type inference."""

    _inventory: DataInventory
    _eligible: EligibleModules

    def __new__(cls, inventory: DataInventory, eligible: EligibleModules) -> Self:
        self = super().__new__(cls)
        self._inventory = inventory
        self._eligible = eligible
        return self

    def findings(self) -> list[Finding]:
        """Attach sorted shared names to each of their eligible owners."""
        entries = ClumpOwners(self._inventory, self._eligible).entries()
        indices: dict[tuple[str, str], int] = {}
        families = []
        for _, _, key in entries:
            if key not in indices:
                indices[key] = len(indices)
            families.append(indices[key])
        sets = [names for _, names, _ in entries]
        return [
            entries[i][0].finding(Rules.DATA_CLUMP, ", ".join(sorted(names)))
            for names, support in ClumpSets(sets, families).repeated()
            for i in support
        ]
