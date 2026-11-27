"""The one command every ratchet gate runs through: parse, run, print."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Protocol, Self

from oo_ratchet.core.domain.errors import StateError

from .gate_options import GateOptions, GateSpec

type Report = tuple[list[str], int]


class Gate(Protocol):
    """What one gate does with its parsed options: report lines and an exit code."""

    def run(self) -> Report:
        """Execute the requested operation."""
        ...


class GateCommand:
    """Parse one gate's command line, run the gate and print its report.

    Locating the repository root can fail while a gate is built; that is a
    failing report, never a traceback.
    """

    _spec: GateSpec
    _build: Callable[[GateOptions], Gate]

    def __new__(cls, spec: GateSpec, build: Callable[[GateOptions], Gate]) -> Self:
        self = super().__new__(cls)
        self._spec = spec
        self._build = build
        return self

    def main(self, argv: list[str] | None = None) -> int:
        """Parse ``argv``, run the gate and return its exit code."""
        options = GateOptions.parse(self._spec, argv)
        try:
            lines, code = self._build(options).run()
        except StateError as exc:
            lines, code = [f"FAIL: {exc}"], 1
        sys.stdout.writelines(line + "\n" for line in lines)
        return code
