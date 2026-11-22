"""Render advisory design results and diagnose invalid scan requests."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Self

from .layer_config import LayerConfigError
from .scanner import DesignScanner


class DesignOutput:
    """Validate a parsed request and render its report without gating findings."""

    _root: Path
    _json: bool
    _layers: Path | None

    def __new__(cls, args: argparse.Namespace) -> Self:
        self = super().__new__(cls)
        self._root = Path(args.src)
        self._json = bool(args.json)
        self._layers = Path(args.layers) if args.layers else None
        return self

    def run(self) -> int:
        """Return 2 for invalid input, never for design findings."""
        if not self._root.is_dir():
            sys.stderr.write(f"oo-ratchet design: {self._root} is not a directory\n")
            return 2
        try:
            sys.stdout.write(self._render())
        except LayerConfigError as exc:
            sys.stderr.write(f"oo-ratchet design: {exc}\n")
            return 2
        return 0

    def _render(self) -> str:
        report = DesignScanner(self._root, self._layers).report
        return report.to_json() + "\n" if self._json else report.to_text()
