"""Command-line entry point for the advisory design check."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Self

from .scanner import DesignScanner


class DesignCli:
    """Parse the design check's arguments and print its report."""

    _root: Path
    _json: bool

    def __new__(cls, argv: list[str] | None) -> Self:
        self = super().__new__(cls)
        ns = cls._parser().parse_args(argv)
        self._root = Path(ns.src)
        self._json = bool(ns.json)
        return self

    def run(self) -> int:
        """Print the report; exit 0 unless the source is not a directory."""
        if not self._root.is_dir():
            sys.stderr.write(f"oo-ratchet design: {self._root} is not a directory\n")
            return 2
        sys.stdout.write(self._render())
        return 0

    def _render(self) -> str:
        report = DesignScanner(self._root).report
        return report.to_json() + "\n" if self._json else report.to_text()

    @staticmethod
    def _parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="oo-ratchet design",
            description=(
                "advisory OO design check: stateless wrapper classes, getter-heavy "
                "classes, concrete imports across package boundaries; never fails"
            ),
        )
        parser.add_argument("src", help="package directory to scan")
        parser.add_argument("--json", action="store_true", help="emit JSON")
        return parser


def main(argv: list[str] | None = None) -> int:
    """Run the advisory design check."""
    return DesignCli(argv).run()
