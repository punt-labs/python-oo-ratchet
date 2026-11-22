"""The value types of the layers gate: an import edge and a violating edge."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, order=True)
class Edge:
    """One module importing another, both as dotted names."""

    source: str
    target: str

    def __str__(self) -> str:
        return f"{self.source} -> {self.target}"


@dataclass(frozen=True, slots=True, order=True)
class Violation:
    """An import edge that crosses from a layer to one it may not import."""

    edge: Edge
    source_layer: str
    target_layer: str

    def __str__(self) -> str:
        return f"{self.edge}  ({self.source_layer} -> {self.target_layer})"
