"""The errors the layers command reports as a one-line failure, not a traceback."""

from __future__ import annotations

from oo_ratchet.coupling.gitio import GitError
from oo_ratchet.design.layer_config import LayerConfigError

from .baseline import LayersBaselineError
from .scan import LayersScanError

FAILURES: tuple[type[Exception], ...] = (
    GitError,
    LayersBaselineError,
    LayerConfigError,
    LayersScanError,
    OSError,
    UnicodeDecodeError,
)
