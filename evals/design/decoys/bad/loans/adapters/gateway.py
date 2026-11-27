"""Library-loan design evaluation fixture."""

from __future__ import annotations


class Gateway:
    """A port implementation: three operations, no fields."""

    def encode(self, raw: dict[str, int]) -> bytes:
        return repr(sorted(raw.items())).encode()

    def decode(self, blob: bytes) -> list[tuple[str, int]]:
        return [(name, 0) for name in blob.decode().split()]

    def checksum(self, blob: bytes) -> int:
        return sum(blob)
