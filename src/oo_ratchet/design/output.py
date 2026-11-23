"""Render advisory design results and diagnose invalid scan requests."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Self

from oo_ratchet.oo.gitio import GitError
from oo_ratchet.source_set import Source, SourceSet

from .scanner import DesignScanner
from .shadow import ShadowCheck


class DesignOutput:
    """Validate a parsed request and render its report without gating findings."""

    _root: Source
    _json: bool
    _layers: Path | None
    _shadow_ref: str | None

    def __new__(cls, args: argparse.Namespace) -> Self:
        self = super().__new__(cls)
        self._root = args.src
        self._json = bool(args.json)
        self._layers = Path(args.layers) if args.layers else None
        self._shadow_ref = args.shadow_check
        return self

    def run(self) -> int:
        """Return 2 for invalid input, never for design findings."""
        if not SourceSet.path(self._root).is_dir():
            sys.stderr.write(f"oo-ratchet design: {self._root} is not a directory\n")
            return 2
        try:
            sys.stdout.write(self._render())
        except (GitError, OSError, ValueError) as exc:
            sys.stderr.write(f"oo-ratchet design: {exc}\n")
            return 2
        return 0

    def _render(self) -> str:
        report = (
            ShadowCheck(self._root, self._layers, self._shadow_ref).report
            if self._shadow_ref is not None
            else DesignScanner(self._root, self._layers).report
        )
        return report.to_json() + "\n" if self._json else report.to_text()
