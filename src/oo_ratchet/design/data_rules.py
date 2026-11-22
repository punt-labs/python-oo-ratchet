"""Compose advisory D1-D4 over one declaration and project-type inventory."""

from __future__ import annotations

from typing import Self

from .clump_rules import ClumpRules
from .data_inventory import DataInventory
from .envy_rules import EnvyRules
from .findings import Finding
from .layer_config import LayerConfig
from .misplaced_rule import MisplacedRule
from .modules import ModuleIndex
from .project_types import ProjectTypes


class DataRules:
    """Keep data placement checks independent of layer-rule configuration presence."""

    _inventory: DataInventory
    _types: ProjectTypes

    def __new__(cls, index: ModuleIndex, config: LayerConfig | None) -> Self:
        self = super().__new__(cls)
        self._inventory = DataInventory(index, config)
        self._types = ProjectTypes(index, self._inventory.declarations())
        return self

    def findings(self) -> list[Finding]:
        """Return the deterministic findings of all four data-design rules."""
        return (
            EnvyRules(self._inventory, self._types).findings()
            + ClumpRules(self._inventory).findings()
            + MisplacedRule(self._inventory, self._types).findings()
        )
