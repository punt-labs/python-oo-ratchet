"""The violating edges of one module: refused imports and domain IO imports."""

from __future__ import annotations

from typing import Self

from oo_ratchet.design.domain_io import DomainIO
from oo_ratchet.design.layer_config import LayerConfig
from oo_ratchet.design.layer_edges import Edge, Violation
from oo_ratchet.design.layer_violations import LayerViolations
from oo_ratchet.design.modules import Module


class ModuleViolations:
    """Edges a module's layer refuses, plus the IO modules a domain module imports.

    An IO import is an edge from the domain module to the IO module (a bare
    ``open`` call is an edge to ``builtins.open``), classed as layer ``io``. It
    applies to the fixed four-layer form only: declared layers have no domain.
    """

    _found: LayerViolations
    _config: LayerConfig

    def __new__(cls, found: LayerViolations, config: LayerConfig) -> Self:
        self = super().__new__(cls)
        self._found = found
        self._config = config
        return self

    def of(self, module: Module) -> set[Violation]:
        """Return the violating edges of ``module``; none if no layer claims it."""
        name = self._found.name(module)
        source = self._config.layer(name)
        if source is None:
            return set()
        edges = {
            Violation(Edge(name, target), source, imported)
            for _, _, target, imported in self._found.refused(module, source)
        }
        if self._config.ORDERED and source == "domain":
            edges.update(
                Violation(Edge(name, io), source, "io")
                for io in DomainIO(module).targets()
            )
        return edges
