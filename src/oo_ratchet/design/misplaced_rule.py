"""Public module functions whose explicit types place them on a project class."""

from __future__ import annotations

import ast
from typing import Self

from oo_ratchet.core.domain.declaration import Declaration
from oo_ratchet.core.domain.findings import Finding, Rules
from oo_ratchet.core.domain.function_shape import FunctionShape
from oo_ratchet.core.domain.project_types import ProjectTypes

from .data_fields import DataFields
from .data_inventory import DataInventory
from .receiver_types import ReceiverTypes


class MisplacedRule:
    """Recognize class-centric signatures, excluding explicitly named factories."""

    _inventory: DataInventory
    _types: ProjectTypes

    def __new__(cls, inventory: DataInventory, types: ProjectTypes) -> Self:
        self = super().__new__(cls)
        self._inventory = inventory
        self._types = types
        return self

    def findings(self) -> list[Finding]:
        """Return findings only for public, non-factory module functions."""
        return [
            owner.finding(
                Rules.MISPLACED_FUNCTION,
                "signature and field reads belong on a project class",
            )
            for owner in self._inventory.declarations()
            if owner.kind == "function"
            and self._inventory.eligible(owner)
            and not owner.node.name.startswith(("_", "create_"))
            and self._placed(owner)
        ]

    def _placed(self, owner: Declaration) -> bool:
        if not isinstance(owner.node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return False
        positional = owner.node.args.posonlyargs + owner.node.args.args
        if positional and self._types.resolve(owner.module, positional[0].annotation):
            return True
        result = self._types.resolve(owner.module, owner.node.returns)
        if result is None:
            return False
        reads = FunctionShape(owner).reads()
        return any(
            target == result and DataFields(result).names() & reads.get(name, set())
            for name, target in ReceiverTypes(owner, self._types).known().items()
        )
