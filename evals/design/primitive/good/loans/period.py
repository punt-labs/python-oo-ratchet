"""Library-loan design evaluation fixture."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Period:
    days: int
    timezone: str = "UTC"
    grace: int = 0

    def due(self) -> int:
        if self.timezone != "UTC":
            raise ValueError("unsupported timezone")
        return max(0, self.days - self.grace) * 2
