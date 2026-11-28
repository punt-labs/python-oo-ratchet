"""Advisory dependency direction, domain purity and entry thinness checks."""

from __future__ import annotations

import ast
from collections.abc import Callable
from typing import ClassVar, Self

from oo_ratchet.core.domain.domain_io import DomainIO
from oo_ratchet.core.domain.findings import Finding, Rules
from oo_ratchet.core.domain.layer_config import LayerConfig
from oo_ratchet.core.domain.layer_violations import LayerViolations
from oo_ratchet.core.domain.modules import Module, ModuleIndex
from oo_ratchet.oo.metrics import ModuleMetrics


class LayerCheck:
    """Apply optional layer declarations without changing existing design rules."""

    EXEMPT: ClassVar[dict[str, frozenset[str]]] = {
        Rules.STATELESS_SINGLE: frozenset({"adapters", "entry"}),
        Rules.STATELESS_BAG: frozenset({"adapters", "entry"}),
        Rules.CONCRETE_IMPORT: frozenset({"entry"}),
    }

    _index: ModuleIndex
    _config: LayerConfig
    _found: LayerViolations

    def __new__(cls, index: ModuleIndex, config: LayerConfig) -> Self:
        self = super().__new__(cls)
        self._index = index
        self._config = config
        self._found = LayerViolations(index, config)
        return self

    def findings(self) -> list[Finding]:
        """Return all configured layer findings in the scanned tree."""
        out: list[Finding] = []
        for module in self._index.modules():
            name = self._found.name(module)
            layer = self._config.layer(name)
            if layer is None:
                out.extend(self._unlayered(module, name))
                continue
            out.extend(self._dependencies(module, layer))
            out.extend(self._shape(module, layer))
        return out

    @classmethod
    def skipper(
        cls, index: ModuleIndex, config: LayerConfig | None
    ) -> Callable[[Module, str], bool]:
        """Return ``skips`` of a check on ``config``; with none, skip nothing."""
        if config is None:
            return lambda _module, _rule: False
        return cls(index, config).skips

    @classmethod
    def configured(
        cls, index: ModuleIndex, config: LayerConfig | None
    ) -> list[Finding]:
        """Return the layer findings of ``config``; with none, there are none."""
        return [] if config is None else cls(index, config).findings()

    @classmethod
    def inward(
        cls, index: ModuleIndex, config: LayerConfig | None
    ) -> Callable[[Module, str], bool]:
        """Return the test of an import pointing at an inner ring; none: never."""
        if config is None:
            return lambda _module, _target: False
        return cls(index, config).points_inward

    def points_inward(self, module: Module, target: str) -> bool:
        """Return whether ``module`` imports ``target`` from a strictly inner ring.

        The Dependency Rule lets an outer ring depend on the entities of an
        inner one, so such an import is not a concrete-class leak. Same-ring,
        outward and unlayered targets are not inward; neither is a config
        without ordered rings.
        """
        if not self._config.ORDERED:
            return False
        source = self._config.layer(self._found.name(module))
        found = self._index.get(target)
        if source is None or found is None:
            return False
        inner = self._config.layer(self._found.name(found))
        order = self._config.ORDER
        return inner is not None and order.index(inner) > order.index(source)

    def skips(self, module: Module, rule: str) -> bool:
        """Return whether ``rule`` is not reported for ``module``'s ring.

        Adapters and the entry ring translate and wire: a stateless codec class
        there is boundary code, not a function-object strategy, and the entry
        ring is the composition root, where importing a concrete adapter is the
        wiring. Only the fixed four-ring form has rings to exempt.
        """
        if not self._config.ORDERED:
            return False
        layer = self._config.layer(self._found.name(module))
        return layer in self.EXEMPT.get(rule, frozenset())

    def _unlayered(self, module: Module, name: str) -> list[Finding]:
        if self._config.EXEMPTS_ROOT and "." not in name:
            return []
        detail = "module matches no layer glob"
        return [module.finding(Rules.UNLAYERED_MODULE, 1, "<module>", detail)]

    def _shape(self, module: Module, layer: str) -> list[Finding]:
        if not self._config.ORDERED:
            return []
        if layer == "domain":
            return DomainIO(module).findings()
        return self._entry(module, module.tree, "") if layer == "entry" else []

    def _dependencies(self, module: Module, layer: str) -> list[Finding]:
        way = "outer " if self._config.ORDERED else ""
        return [
            module.finding(
                Rules.LAYER_IMPORT,
                node.lineno,
                symbol,
                f"{layer} imports {way}{imported} module {target}",
            )
            for node, symbol, target, imported in self._found.refused(module, layer)
        ]

    def _entry(self, module: Module, scope: ast.AST, prefix: str) -> list[Finding]:
        out: list[Finding] = []
        for node in ast.iter_child_nodes(scope):
            name = prefix
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + node.name + "."
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                complexity = ModuleMetrics._cyclomatic_complexity(node)
                if complexity > 4:
                    out.append(
                        module.finding(
                            Rules.THICK_ENTRY,
                            node.lineno,
                            name[:-1],
                            f"entry complexity {complexity} > 4",
                        )
                    )
            out.extend(self._entry(module, node, name))
        return out
