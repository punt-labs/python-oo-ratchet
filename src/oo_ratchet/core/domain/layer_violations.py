"""The import edges a layer config refuses, found in one indexed package."""

from __future__ import annotations

import ast
from typing import Self

from .layer_config import LayerConfig
from .layer_imports import LayerImports
from .modules import Module, ModuleIndex

type Site = ast.stmt | ast.expr
type Refusal = tuple[Site, str, str, str]


class LayerViolations:
    """Resolve each module's imports and keep the ones its layer may not make."""

    _index: ModuleIndex
    _config: LayerConfig
    _imports: LayerImports

    def __new__(cls, index: ModuleIndex, config: LayerConfig) -> Self:
        self = super().__new__(cls)
        self._index = index
        self._config = config
        self._imports = LayerImports(index)
        return self

    def name(self, module: Module) -> str:
        """Return the dotted name the config classifies ``module`` by."""
        return self._imports.canonical_name(module)

    def targets(self, module: Module) -> list[tuple[Site, str, str]]:
        """Return ``(site, symbol, target module)`` for each resolved import."""
        rows = self._imports.imports(module)
        return [(node, symbol, target) for node, symbol, target in rows]

    def refused(self, module: Module, layer: str) -> list[Refusal]:
        """Return ``(site, symbol, target, target layer)`` per refused import."""
        rows: list[Refusal] = []
        for node, symbol, target in self.targets(module):
            imported = self._config.layer(target)
            if imported is not None and imported not in self._config.allowed(layer):
                rows.append((node, symbol, target, imported))
        return rows
