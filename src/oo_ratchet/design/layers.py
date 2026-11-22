"""Advisory dependency direction, domain purity and entry thinness checks."""

from __future__ import annotations

import ast
from typing import Self

from oo_ratchet.oo.metrics import ModuleMetrics

from .domain_io import DomainIO
from .findings import Finding, Rules
from .layer_config import LayerConfig
from .layer_imports import LayerImports
from .modules import Module, ModuleIndex


class LayerCheck:
    """Apply optional layer declarations without changing existing design rules."""

    _index: ModuleIndex
    _config: LayerConfig
    _imports: LayerImports

    def __new__(cls, index: ModuleIndex, config: LayerConfig) -> Self:
        self = super().__new__(cls)
        self._index = index
        self._config = config
        self._imports = LayerImports(index)
        return self

    def findings(self) -> list[Finding]:
        """Return all configured layer findings in the scanned tree."""
        out: list[Finding] = []
        for module in self._index.modules():
            layer = self._config.layer(self._imports.canonical_name(module))
            if layer is None:
                out.append(
                    self._finding(
                        module,
                        Rules.UNLAYERED_MODULE,
                        1,
                        "<module>",
                        "module matches no layer glob",
                    )
                )
                continue
            out.extend(self._dependencies(module, layer))
            if layer == "domain":
                out.extend(DomainIO(module).findings())
            if layer == "entry":
                out.extend(self._entry(module, module.tree, ""))
        return out

    def _dependencies(self, module: Module, layer: str) -> list[Finding]:
        out: list[Finding] = []
        for node, symbol, target in self._imports.imports(module):
            imported = self._config.layer(target)
            if imported is not None and LayerConfig.ORDER.index(
                imported
            ) < LayerConfig.ORDER.index(layer):
                out.append(
                    self._finding(
                        module,
                        Rules.LAYER_IMPORT,
                        node.lineno,
                        symbol,
                        f"{layer} imports outer {imported} module {target}",
                    )
                )
        return out

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
