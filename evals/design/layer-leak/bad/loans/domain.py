"""Library-loan design evaluation fixture."""

from __future__ import annotations

import json

from .adapters.store import FeeStore


def rate() -> int:
    encoded = json.dumps(FeeStore().rate())
    return int(encoded)
