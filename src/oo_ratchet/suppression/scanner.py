"""Scan a file or directory tree for suppression comments."""

from __future__ import annotations

import tokenize
from pathlib import Path
from typing import Self

from oo_ratchet.source_set import Source, SourceSelection

from .patterns import FileSuppressions
from .pyproject import PerFileIgnoresCounter
from .report import SuppressionReport


class Scanner:
    """Discover Python files under a target and build a suppression report."""

    _report: SuppressionReport

    def __new__(cls, target: Source, project_root: Path | None = None) -> Self:
        self = super().__new__(cls)
        root = project_root if project_root is not None else Path.cwd()
        file_results = self._collect_files(target)
        pfi = PerFileIgnoresCounter(root / "pyproject.toml")
        report = SuppressionReport.from_files(file_results, pfi.total, pfi.breakdown)
        if SourceSelection(target).namespace is not None:
            # A namespace report keys files relative to the project root.
            report = SuppressionReport.rebased(report, str(root.resolve()) + "/", "")
        self._report = report
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
    def _collect_files(target: Source) -> list[FileSuppressions]:
        return [
            FileSuppressions(str(p), Scanner._read(p))
            for p in SourceSelection(target).files()
        ]
