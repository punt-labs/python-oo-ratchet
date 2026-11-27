"""Render advisory design results and diagnose invalid scan requests."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Self

from oo_ratchet.core.domain.errors import GitError
from oo_ratchet.source_set import Source, SourceSet

from .enforcement.output import DesignRun


class DesignOutput:
    """Validate a parsed request and render its report without gating findings."""

    _root: Source
    _json: bool
    _layers: Path | None
    _shadow_ref: str | None
    _enforce: bool

    def __new__(cls, args: argparse.Namespace) -> Self:
        self = super().__new__(cls)
        self._root = args.src
        self._json = bool(args.json)
        self._layers = Path(args.layers) if args.layers else None
        self._shadow_ref = args.shadow_check
        self._enforce = bool(args.enforce)
        return self

    def run(self) -> int:
        """Return 2 for invalid input, 1 for an enforced finding, else 0."""
        if not SourceSet.path(self._root).is_dir():
            sys.stderr.write(f"oo-ratchet design: {self._root} is not a directory\n")
            return 2
        try:
            design = DesignRun(
                self._root, self._layers, self._shadow_ref, enforce=self._enforce
            )
            sys.stdout.write(design.render(as_json=self._json))
            return design.status()
        except (GitError, OSError, ValueError) as exc:
            sys.stderr.write(f"oo-ratchet design: {exc}\n")
            return 2
