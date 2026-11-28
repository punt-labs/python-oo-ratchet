"""A shadow scan that measures OO metrics by reading the scanned tree."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from oo_ratchet.oo.tree import Scorer
from oo_ratchet.source_set import Source

from .shadow_scan import ShadowScan


class TreeScan(ShadowScan):
    """A ``ShadowScan`` whose OO scores come from ``Scorer`` over the files."""

    def __new__(
        cls,
        source: Source,
        repo: Path,
        layers: Path | None,
        *,
        package_name: str | None = None,
    ) -> Self:
        return super().__new__(
            cls, source, repo, layers, score=Scorer, package_name=package_name
        )
