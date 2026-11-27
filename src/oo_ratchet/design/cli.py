"""Command-line entry point for the advisory design check."""

from __future__ import annotations

import argparse
from typing import Self

from oo_ratchet.source_set import SourceSet

from .output import DesignOutput


class DesignCli:
    """Parse the design check's arguments and print its report."""

    _output: DesignOutput

    def __new__(cls, argv: list[str] | None) -> Self:
        self = super().__new__(cls)
        self._output = DesignOutput(SourceSet.parse(cls._parser(), argv))
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
        SourceSet.add(parser)
        parser.add_argument("--json", action="store_true", help="emit JSON")
        parser.add_argument("--layers", help="TOML layer configuration override")
        parser.add_argument(
            "--shadow-check",
            metavar="GIT_REF",
            help="compare merge-base debt, advisory unless --enforce",
        )
        parser.add_argument(
            "--enforce",
            action="store_true",
            help="with --shadow-check, exit 1 on an added finding of a "
            "gate-capable rule (layer-import, size-cap, thick-entry, "
            "unlayered-module, stateless-single-method)",
        )
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
