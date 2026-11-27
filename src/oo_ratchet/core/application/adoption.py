"""The two questions a gate's first adoption turns on."""

from __future__ import annotations

from typing import Protocol


class Adoption(Protocol):
    """What a gate's history tells about adoption: bases and recorded state."""

    def resolve(self, ref: str | None) -> str | None:
        """Return the commit a ref names, ``None`` if it names none."""
        ...

    def adopted_at(self, ref: str) -> bool:
        """Return whether the gate's recorded state exists at ``ref``."""
        ...


class Presence(Protocol):
    """Whether an in-tree baseline exists."""

    def exists(self) -> bool:
        """Return whether a baseline is present."""
        ...
