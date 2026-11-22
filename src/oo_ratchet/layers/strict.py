"""The layers gate's view of a package: every edge the design check can miss."""

from __future__ import annotations

import ast
from typing import Self

from oo_ratchet.design.layer_config import LayerConfig
from oo_ratchet.design.layer_edges import Edge, Violation
from oo_ratchet.design.layer_violations import LayerViolations, Site
from oo_ratchet.design.modules import Module, ModuleIndex

from .dynamic import DynamicImports
from .exports import Reexports

_HOPS = 8


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

    def __new__(cls, index: ModuleIndex, config: LayerConfig) -> Self:
        self = super().__new__(cls, index, config)
        self._by_name = {self.name(m): m for m in index.modules()}
        return self

    def targets(self, module: Module) -> list[tuple[Site, str, str]]:
        """Return the design check's edges plus re-exported and dynamic ones."""
        rows = super().targets(module)
        for node, symbol, target in list(rows):
            rows.extend((node, symbol, hop) for hop in self._hops(target, symbol))
        rows.extend(DynamicImports(module.tree, self._by_name).targets())
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
        """Return the non-root modules that match no layer."""
        names = (self.name(m) for m in self._index.modules())
        return sorted(n for n in names if "." in n and self._config.layer(n) is None)

    def unresolvable(self) -> list[str]:
        """Return ``path:line`` for each relative import that climbs past the root."""
        found: list[str] = []
        for module in self._index.modules():
            parts = self.name(module).split(".")
            depth = len(parts) if module.is_package else len(parts) - 1
            found.extend(
                f"{module.path}:{node.lineno}"
                for node in ast.walk(module.tree)
                if isinstance(node, ast.ImportFrom) and node.level > depth
            )
        return sorted(found)

    def _hops(self, target: str, symbol: str) -> list[str]:
        """Follow ``symbol`` through the package ``__init__`` files re-exporting it."""
        hops: list[str] = []
        for _ in range(_HOPS):
            module = self._by_name.get(target)
            if module is None or not module.is_package:
                break
            exports = Reexports(module.tree, super().targets(module), self._by_name)
            source = exports.get(symbol)
            if source is None or source[0] == target:
                break
            target, symbol = source
            hops.append(target)
        return hops
