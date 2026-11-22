"""The gates the ``oo-ratchet`` command can run, by name."""

from __future__ import annotations

from collections.abc import Callable

from oo_ratchet.coupling.cli import main as coupling_main
from oo_ratchet.design.cli import main as design_main
from oo_ratchet.layers.cli import main as layers_main
from oo_ratchet.oo.cli import main as oo_main
from oo_ratchet.suppression.cli import main as suppression_main

GATES: dict[str, Callable[[list[str] | None], int]] = {
    "oo": oo_main,
    "coupling": coupling_main,
    "suppressions": suppression_main,
    "design": design_main,
    "layers": layers_main,
}
