"""Command-line entry point for the advisory design check."""

from __future__ import annotations

import argparse
from typing import Self

from .output import DesignOutput


class DesignCli:
    """Parse the design check's arguments and print its report."""

    _output: DesignOutput

    def __new__(cls, argv: list[str] | None) -> Self:
        self = super().__new__(cls)
        self._output = DesignOutput(cls._parser().parse_args(argv))
        return self

    def run(self) -> int:
        """Print the advisory report or an input error."""
        return self._output.run()

    @classmethod
    def _parser(cls) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="oo-ratchet design",
            description=cls._description(),
        )
        parser.add_argument("src", help="package directory to scan")
        parser.add_argument("--json", action="store_true", help="emit JSON")
        parser.add_argument("--layers", help="TOML layer configuration override")
        return parser

    @staticmethod
    def _description() -> str:
        return (
            "Advisory OO design and optional layer checks. Findings never fail; "
            "invalid paths or layer configuration exit 2."
        )


def main(argv: list[str] | None = None) -> int:
    """Run the advisory design check."""
    return DesignCli(argv).run()
