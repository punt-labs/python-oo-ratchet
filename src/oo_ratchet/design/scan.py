"""Assemble class, boundary and optional layer checks over a package tree."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from oo_ratchet.core.domain.layer_table import LayerTable
from oo_ratchet.core.domain.modules import ModuleIndex
from oo_ratchet.source_set import SourceSelection

from .boundaries import BoundaryCheck
from .class_rules import ClassRules
from .data_rules import DataRules
from .layers import LayerCheck
from .report import DesignReport

if TYPE_CHECKING:
    from pathlib import Path

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
        source = SourceSelection(root)
        index = ModuleIndex(source, package_name=package_name)
        self._index = index
        config = source.layer_table(layers).config()
        skips = LayerCheck.skipper(index, config)
        class_rules = ClassRules(index.interface_methods(), skips)
        findings = [f for m in index.modules() for f in class_rules.findings(m)]
        findings.extend(BoundaryCheck(index).findings(skips))
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
