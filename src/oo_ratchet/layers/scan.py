"""Scan one package with the design gate's layer check, for the layers gate."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from oo_ratchet.design.layer_config import LayerConfigError
from oo_ratchet.design.layer_edges import Edge, Violation
from oo_ratchet.design.layer_table import LayerTable
from oo_ratchet.design.layer_violations import LayerViolations
from oo_ratchet.design.modules import ModuleIndex


class LayersScanError(Exception):
    """A module of the package could not be read or parsed."""


class LayerScan:
    """The violating import edges of one package under a layer config.

    ``src`` is the package directory itself (``src/pkg``). The config is read
    from the nearest ``pyproject.toml`` above it; a missing
    ``[tool.oo-ratchet.layers]`` table is an error because the gate has nothing
    to enforce. Classification and import resolution are the design gate's, so
    ``oo-ratchet design`` and ``oo-ratchet layers`` always agree. Like the
    design gate, imports under ``TYPE_CHECKING`` count as edges. A module the
    scan could not parse fails the scan instead of silently dropping its edges.
    """

    _modules: tuple[str, ...]
    _violations: tuple[Violation, ...]
    _unassigned: tuple[str, ...]

    def __new__(cls, src: Path) -> Self:
        self = super().__new__(cls)
        config = LayerTable.load(src)
        if config is None:
            msg = f"no [tool.oo-ratchet.layers] table above {src}"
            raise LayerConfigError(msg)
        index = ModuleIndex(src)
        if index.skipped:
            names = ", ".join(sorted(str(p) for p in index.skipped))
            msg = f"cannot read or parse: {names}"
            raise LayersScanError(msg)
        found = LayerViolations(index, config)
        self._modules = tuple(sorted(found.name(m) for m in index.modules()))
        self._violations = tuple(found.violations())
        self._unassigned = tuple(found.unassigned())
        return self

    @property
    def modules(self) -> tuple[str, ...]:
        """Return the scanned module names, sorted."""
        return self._modules

    @property
    def violations(self) -> tuple[Violation, ...]:
        """Return the edges whose source layer may not import the target layer."""
        return self._violations

    @property
    def edges(self) -> frozenset[Edge]:
        """Return the violating edges."""
        return frozenset(v.edge for v in self._violations)

    @property
    def unassigned(self) -> tuple[str, ...]:
        """Return the non-exempt modules that match no layer."""
        return self._unassigned
