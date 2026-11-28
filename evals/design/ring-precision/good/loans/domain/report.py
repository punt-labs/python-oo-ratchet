"""Library-loan design evaluation fixture."""

from __future__ import annotations

import io


def render(days: int) -> str:
    buffer = io.StringIO()
    buffer.write(f"{days} days")
    return buffer.getvalue()
