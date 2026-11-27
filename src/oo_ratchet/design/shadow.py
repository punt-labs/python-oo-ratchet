"""Choose a legacy package scan or a joined namespace shadow scan."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from oo_ratchet.source_set import Source, SourceSelection

from .legacy_shadow import LegacyShadow
from .namespace_shadow import NamespaceShadow
from .shadow_report import ShadowReport


class ShadowCheck:
    """Compare the same logical source selection on either side of a merge base."""

    _report: ShadowReport

    def __new__(cls, source: Source, layers: Path | None, ref: str) -> Self:
        self = super().__new__(cls)
        selection = SourceSelection(source)
        self._report = selection.select(
            lambda path: LegacyShadow(path, layers, ref).report,
            lambda _: NamespaceShadow(selection, layers, ref).report,
        )
        return self

    @property
    def report(self) -> ShadowReport:
        """Return the measured, advisory comparison."""
        return self._report
