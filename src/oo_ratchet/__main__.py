"""``oo-ratchet <gate> <src> [flags]`` — dispatch to one of the ratchets."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from typing import ClassVar, Self

from oo_ratchet import __version__
from oo_ratchet.coupling.cli import main as coupling_main
from oo_ratchet.design.cli import main as design_main
from oo_ratchet.layers.cli import main as layers_main
from oo_ratchet.logging_config import DiagnosticLog, LoggingSetupError
from oo_ratchet.oo.cli import main as oo_main
from oo_ratchet.suppression.cli import main as suppression_main
from oo_ratchet.usage import Usage

logger = logging.getLogger(__name__)


class Dispatcher:
    """Route one command line to the gate its first argument names."""

    GATES: ClassVar[dict[str, Callable[[list[str] | None], int]]] = {
        "oo": oo_main,
        "coupling": coupling_main,
        "suppressions": suppression_main,
        "design": design_main,
        "layers": layers_main,
    }
    USAGE: ClassVar[str] = (
        "usage: oo-ratchet {oo,coupling,suppressions,design,layers} <src> [flags]\n"
        "       oo-ratchet <gate> --help for that gate's flags"
    )

    _args: list[str]

    def __new__(cls, argv: list[str] | None) -> Self:
        self = super().__new__(cls)
        self._args = sys.argv[1:] if argv is None else argv
        return self

    def run(self) -> int:
        """Run the named gate, or answer ``--help``/``--version`` itself."""
        if not self._args or self._args[0] in {"-h", "--help"}:
            return self._usage()
        if self._args[0] == "--version":
            sys.stdout.write(f"oo-ratchet {__version__}\n")
            return 0
        return self._dispatch(self._args[0])

    def _usage(self) -> int:
        sys.stdout.write(self.USAGE + "\n")
        return 0 if self._args else 2

    def _dispatch(self, name: str) -> int:
        gate = self.GATES.get(name)
        if gate is None:
            sys.stderr.write(f"oo-ratchet: unknown gate {name!r}\n{self.USAGE}\n")
            return 2
        try:
            DiagnosticLog().configure()
        except LoggingSetupError as exc:
            sys.stderr.write(f"oo-ratchet: cannot open the diagnostic log: {exc}\n")
            return 2
        logger.info("Running %s gate (oo-ratchet %s)", name, __version__)
        usage = Usage(self.GATES)
        usage.start()
        try:
            return usage.run(name, lambda: gate(self._args[1:]))
        finally:
            usage.stop()


def main(argv: list[str] | None = None) -> int:
    """Run the gate named by the first argument with the remaining arguments."""
    return Dispatcher(argv).run()


if __name__ == "__main__":
    sys.exit(main())
