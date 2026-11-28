"""Read a target's files and pyproject, and build its suppression report."""

from __future__ import annotations

import tokenize
from pathlib import Path
from typing import Self

from oo_ratchet.source_set import Source, SourceSelection

from .census import SuppressionCensus
from .pyproject import PerFileIgnoresCounter
from .report import SuppressionReport


class Scanner:
    """Discover Python files under a target and build a suppression report."""

    _report: SuppressionReport

    def __new__(cls, target: Source, project_root: Path | None = None) -> Self:
        self = super().__new__(cls)
        root = project_root if project_root is not None else Path.cwd()
        file_results = SuppressionCensus(self._read_all(target)).files
        pfi = PerFileIgnoresCounter(root / "pyproject.toml")
        report = SuppressionReport.from_files(file_results, pfi.total, pfi.breakdown)
        # A namespace report keys files relative to the project root.
        self._report = SourceSelection(target).select(
            lambda _: report,
            lambda _: SuppressionReport.rebased(report, str(root.resolve()) + "/", ""),
        )
        return self

    @property
    def report(self) -> SuppressionReport:
        """Return the aggregated suppression report."""
        return self._report

    @staticmethod
    def _read(path: Path) -> str:
        """Decode ``path`` honoring its PEP 263 coding cookie.

        Without a usable cookie it is read as strict UTF-8, so undecodable
        bytes still raise and the CLI fails closed.
        """
        try:
            with tokenize.open(path) as f:
                return f.read()
        except SyntaxError:
            return path.read_text(encoding="utf-8")

    @staticmethod
    def _read_all(target: Source) -> dict[str, str]:
        return {str(p): Scanner._read(p) for p in SourceSelection(target).files()}
