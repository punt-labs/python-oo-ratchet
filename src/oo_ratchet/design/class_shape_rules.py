"""Forwarding and method-connectivity findings on class declarations."""

from __future__ import annotations

from typing import Self

from .data_inventory import DataInventory
from .findings import Finding, Rules
from .method_graph import MethodGraph
from .middle_man import MiddleMan
from .project_types import ProjectTypes


class ClassShapeRules:
    """Keep shape findings independent of the data-placement layer exclusions."""

    _inventory: DataInventory
    _types: ProjectTypes

    def __new__(cls, inventory: DataInventory, types: ProjectTypes) -> Self:
        self = super().__new__(cls)
        self._inventory = inventory
        self._types = types
        return self

    def findings(self) -> list[Finding]:
        """Return class-keyed D7 and D8 findings."""
        findings = []
        for owner in self._inventory.declarations():
            if owner.kind != "class":
                continue
            if MiddleMan(owner, self._types).found():
                findings.append(
                    owner.finding(
                        Rules.MIDDLE_MAN,
                        "public methods only forward to one collaborator",
                    )
                )
            components = MethodGraph(owner).components()
            if components > 1:
                findings.append(
                    owner.finding(Rules.SPLIT_COHESION, f"LCOM4={components}")
                )
        return findings
