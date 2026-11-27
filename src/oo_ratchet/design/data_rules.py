"""Compose advisory data and shape checks over one declaration/type inventory."""

from __future__ import annotations

from typing import Self

from oo_ratchet.core.domain.findings import Finding
from oo_ratchet.core.domain.layer_config import LayerConfig
from oo_ratchet.core.domain.modules import ModuleIndex
from oo_ratchet.core.domain.project_types import ProjectTypes

from .clump_rules import ClumpRules
from .data_inventory import DataInventory
from .envy_rules import EnvyRules
from .misplaced_rule import MisplacedRule
from .shape_rules import ShapeRules


class DataRules:
    """Keep data placement checks independent of layer-rule configuration presence."""

    _inventory: DataInventory
    _types: ProjectTypes
    _shapes: ShapeRules

    def __new__(cls, index: ModuleIndex, config: LayerConfig | None) -> Self:
        self = super().__new__(cls)
        self._inventory = DataInventory(index, config)
        self._types = ProjectTypes(index, self._inventory.declarations())
        self._shapes = ShapeRules(self._inventory, self._types, index, config)
        return self

    def findings(self) -> list[Finding]:
        """Return deterministic data-placement, shape and size findings."""
        return (
            EnvyRules(self._inventory, self._types).findings()
            + ClumpRules(self._inventory).findings()
            + MisplacedRule(self._inventory, self._types).findings()
            + self._shapes.findings()
        )
