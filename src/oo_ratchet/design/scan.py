"""Assemble class, boundary and optional layer checks over a package tree."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Self

from .boundaries import BoundaryCheck
from .class_rules import ClassRules
from .data_rules import DataRules
from .layer_table import LayerTable
from .layers import LayerCheck
from .modules import ModuleIndex
from .report import DesignReport

if TYPE_CHECKING:
    from oo_ratchet.source_set import Source


class DesignScanner:
    """Index a package tree once and collect the findings of every rule."""

    _report: DesignReport
    _index: ModuleIndex

    def __new__(
        cls,
        root: Source,
        layers: Path | None = None,
        *,
        package_name: str | None = None,
    ) -> Self:
        self = super().__new__(cls)
        index = ModuleIndex(root, package_name=package_name)
        self._index = index
        class_rules = ClassRules(index.interface_methods())
        findings = [f for m in index.modules() for f in class_rules.findings(m)]
        findings.extend(BoundaryCheck(index).findings())
        config = LayerTable.load(root, layers)
        findings.extend(DataRules(index, LayerTable.ordered(config)).findings())
        if config is not None:
            findings.extend(LayerCheck(index, config).findings())
        self._report = DesignReport(findings, index.skipped, len(index.modules()))
        return self

    @property
    def report(self) -> DesignReport:
        """Return the collected report."""
        return self._report

    def module_key(self, path: Path) -> str:
        """Return the same unique file identity used by the rule inventories."""
        return self._index.key_for(path)
