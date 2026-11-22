"""The import edges a layer config refuses, found in one indexed package."""

from __future__ import annotations

import ast
from typing import Self

from .layer_config import LayerConfig
from .layer_edges import Edge, Violation
from .layer_imports import LayerImports
from .modules import Module, ModuleIndex


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

    def refused(
        self, module: Module, layer: str
    ) -> list[tuple[ast.stmt, str, str, str]]:
        """Return ``(node, symbol, target, target layer)`` for each refused import."""
        rows: list[tuple[ast.stmt, str, str, str]] = []
        for node, symbol, target in self._imports.imports(module):
            imported = self._config.layer(target)
            if imported is not None and imported not in self._config.allowed(layer):
                rows.append((node, symbol, target, imported))
        return rows

    def violations(self) -> list[Violation]:
        """Return every refused edge, one per source and target module."""
        found: set[Violation] = set()
        for module in self._index.modules():
            source = self._config.layer(self.name(module))
            if source is None:
                continue
            found.update(
                Violation(Edge(self.name(module), target), source, imported)
                for _, _, target, imported in self.refused(module, source)
            )
        return sorted(found)

    def unassigned(self) -> list[str]:
        """Return the layerless modules that the config does not exempt."""
        names = (self.name(m) for m in self._index.modules())
        return sorted(
            n
            for n in names
            if self._config.layer(n) is None
            and not (self._config.EXEMPTS_ROOT and "." not in n)
        )
