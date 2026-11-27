"""The layers gate's edge extractor: every edge the design check can miss."""

from __future__ import annotations

from functools import partial
from typing import Self

from oo_ratchet.core.domain.layer_config import LayerConfig
from oo_ratchet.core.domain.layer_violations import LayerViolations, Site
from oo_ratchet.core.domain.modules import Module, ModuleIndex

from .chain import ExportChain
from .dynamic import DynamicImports


class StrictViolations(LayerViolations):
    """Design-check edges plus re-export hops and literal dynamic imports.

    ``from pkg import X`` where a package ``__init__`` re-exports ``X`` from
    another module is an edge to the module that defines ``X``, not only to the
    package: following the re-export reports the true target layer, where
    counting every layer the root imports would flag edges nobody wrote.
    ``importlib.import_module("pkg.a")`` and ``__import__("pkg.a")`` with a
    string literal are edges too. Computed names and attribute access on an
    imported package are out of scope.
    """

    _by_name: dict[str, Module]
    _chain: ExportChain

    def __new__(cls, index: ModuleIndex, config: LayerConfig) -> Self:
        self = super().__new__(cls, index, config)
        self._by_name = {self.name(m): m for m in index.modules()}
        self._chain = ExportChain(self._by_name, partial(LayerViolations.targets, self))
        return self

    def targets(self, module: Module) -> list[tuple[Site, str, str]]:
        """Return the design check's edges plus re-exported and dynamic ones."""
        rows = super().targets(module)
        for node, symbol, target in list(rows):
            rows.extend(
                (node, symbol, hop) for hop in self._chain.follow(target, symbol)
            )
        rows.extend(DynamicImports(module.tree, self._by_name).targets())
        return rows
