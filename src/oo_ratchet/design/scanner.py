"""Run every design rule over one package tree."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from .boundaries import BoundaryCheck
from .class_rules import ClassRules
from .modules import ModuleIndex
from .report import DesignReport


class DesignScanner:
    """Index a package tree once and collect the findings of every rule."""

    _report: DesignReport

    def __new__(cls, root: Path) -> Self:
        self = super().__new__(cls)
        index = ModuleIndex(root)
        class_rules = ClassRules(index.interface_methods())
        findings = [f for m in index.modules() for f in class_rules.findings(m)]
        findings.extend(BoundaryCheck(index).findings())
        self._report = DesignReport(findings, index.skipped, len(index.modules()))
        return self

    @property
    def report(self) -> DesignReport:
        """Return the collected report."""
        return self._report
