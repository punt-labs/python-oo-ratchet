"""The errors the layers command reports as a one-line failure, not a traceback."""

from __future__ import annotations

from oo_ratchet.core.domain.errors import StateError
from oo_ratchet.design.layer_config import LayerConfigError

from .scan import LayersScanError

FAILURES: tuple[type[Exception], ...] = (
    StateError,
    LayerConfigError,
    LayersScanError,
    OSError,
    UnicodeDecodeError,
)
