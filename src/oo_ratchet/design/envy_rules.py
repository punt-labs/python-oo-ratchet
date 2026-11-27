"""External data consumers and parameter-centric behavior placement."""

from __future__ import annotations

from typing import Self

from oo_ratchet.core.domain.declaration import Declaration
from oo_ratchet.core.domain.findings import Finding, Rules
from oo_ratchet.core.domain.function_shape import FunctionShape
from oo_ratchet.core.domain.project_types import ProjectTypes

from .data_fields import DataFields
from .data_inventory import DataInventory
from .eligible_modules import EligibleModules
from .receiver_types import ReceiverTypes


class EnvyRules:
    """Apply D1 and D2 to explicitly typed receivers, never inferred aliases."""

    _inventory: DataInventory
    _eligible: EligibleModules
    _types: ProjectTypes

    def __new__(
        cls,
        inventory: DataInventory,
        eligible: EligibleModules,
        types: ProjectTypes,
    ) -> Self:
        self = super().__new__(cls)
        self._inventory = inventory
        self._eligible = eligible
        self._types = types
        return self

    def findings(self) -> list[Finding]:
        """Report envied classes once and feature envy once per function."""
        envied: dict[tuple[str, str], Finding] = {}
        out: list[Finding] = []
        for owner in self._inventory.declarations():
            if owner.kind == "class" or not self._eligible.holds(owner):
                continue
            known = ReceiverTypes(owner, self._types).known()
            for target in self._envied(owner, known):
                envied[target.module.key, target.symbol] = target.finding(
                    Rules.ENVIED_DATA, "two or more fields read in another module"
                )
            out.extend(self._feature(owner, known))
        return list(envied.values()) + out

    def _envied(
        self, owner: Declaration, known: dict[str, Declaration]
    ) -> list[Declaration]:
        reads = FunctionShape(owner).reads()
        return [
            target
            for name, target in known.items()
            if target.module.key != owner.module.key
            and self._eligible.holds(target)
            and DataFields(target).data_only()
            and len(reads.get(name, set()) & DataFields(target).names()) >= 2
        ]

    @staticmethod
    def _feature(owner: Declaration, known: dict[str, Declaration]) -> list[Finding]:
        shape = FunctionShape(owner)
        if shape.decoder():
            return []
        reads = shape.reads()
        own = len(reads.get("self", set())) if owner.kind == "method" else 0
        parameters = {a.arg for a in shape.parameters()} - {"self", "cls"}
        candidates = sorted(
            name
            for name in parameters & known.keys()
            if len(reads.get(name, set())) >= 3 and len(reads[name]) > own
        )
        return (
            [
                owner.finding(
                    Rules.FEATURE_ENVY,
                    "parameter attributes dominate: " + ", ".join(candidates),
                )
            ]
            if candidates
            else []
        )
