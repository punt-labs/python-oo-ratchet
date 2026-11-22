"""Compose advisory shape rules over the existing declaration/type inventory."""

from __future__ import annotations

from typing import Self

from .class_shape_rules import ClassShapeRules
from .data_inventory import DataInventory
from .findings import Finding
from .layer_config import LayerConfig
from .layer_imports import LayerImports
from .modules import ModuleIndex
from .project_types import ProjectTypes
from .signature_rules import SignatureRules
from .size_rules import SizeRules


class ShapeRules:
    """Reuse project classes without introducing scope or flow inference."""

    _signatures: SignatureRules
    _classes: ClassShapeRules
    _sizes: SizeRules

    def __new__(
        cls,
        inventory: DataInventory,
        types: ProjectTypes,
        index: ModuleIndex,
        config: LayerConfig | None,
    ) -> Self:
        self = super().__new__(cls)
        names = LayerImports(index)
        layers = (
            {m.key: config.layer(names.name(m)) for m in index.modules()}
            if config is not None
            else {}
        )
        self._signatures = SignatureRules(inventory, layers)
        self._classes = ClassShapeRules(inventory, types)
        self._sizes = SizeRules(index, inventory)
        return self

    def findings(self) -> list[Finding]:
        """Collect D5-D8 and all Tier 0 cap findings."""
        return (
            self._signatures.findings()
            + self._classes.findings()
            + self._sizes.findings()
        )
