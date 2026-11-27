"""Advisory dependency direction, domain purity and entry thinness checks."""

from __future__ import annotations

import ast
from collections.abc import Callable
from typing import ClassVar, Self

from oo_ratchet.oo.metrics import ModuleMetrics

from .domain_io import DomainIO
from .findings import Finding, Rules
from .layer_config import LayerConfig
from .layer_violations import LayerViolations
from .modules import Module, ModuleIndex


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
        return [self._finding(module, Rules.UNLAYERED_MODULE, 1, "<module>", detail)]

    def _shape(self, module: Module, layer: str) -> list[Finding]:
        if not self._config.ORDERED:
            return []
        if layer == "domain":
            return DomainIO(module).findings()
        return self._entry(module, module.tree, "") if layer == "entry" else []

    def _dependencies(self, module: Module, layer: str) -> list[Finding]:
        way = "outer " if self._config.ORDERED else ""
        return [
            self._finding(
                module,
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
                        self._finding(
                            module,
                            Rules.THICK_ENTRY,
                            node.lineno,
                            name[:-1],
                            f"entry complexity {complexity} > 4",
                        )
                    )
            out.extend(self._entry(module, node, name))
        return out

    @staticmethod
    def _finding(
        module: Module, rule: str, line: int, symbol: str, detail: str
    ) -> Finding:
        return Finding(rule, str(module.path), line, symbol, detail)
