"""Library-loan design evaluation fixture."""

from __future__ import annotations

import io


def render(path: str) -> str:
    return io.FileIO(path).readall().decode()
