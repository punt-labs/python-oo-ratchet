"""Render ring assignments as a ``[tool.oo-ratchet.layers]`` table."""

from __future__ import annotations

import glob
from typing import ClassVar, Self

from .suggest_text import SafeText


class RingTable:
    """The fixed four-layer table for modules already given a ring.

    The gate matches every entry with ``fnmatchcase``, so ``[``, ``*`` and ``?``
    in a module name are escaped (``glob.escape``) and match only themselves.
    Names are explicit except where a prefix is exact: ``pkg.sub`` and
    ``pkg.sub.*`` are emitted only when every scanned module equal to or under
    ``pkg.sub`` is in the same ring, so the glob claims nothing it should not.
    """

    ORDER: ClassVar[tuple[str, ...]] = ("entry", "adapters", "application", "domain")
    _modules: tuple[str, ...]
    _rings: dict[str, str]

    def __new__(cls, modules: list[str], rings: dict[str, str]) -> Self:
        self = super().__new__(cls)
        self._modules = tuple(sorted(modules))
        self._rings = rings
        return self

    def render(self) -> list[str]:
        """Return the TOML lines of the table: rings in order, entries sorted."""
        lines = ["[tool.oo-ratchet.layers]"]
        for ring in self.ORDER:
            entries = self._entries(ring)
            if not entries:
                lines.append(f"{ring} = []")
                continue
            lines.append(f"{ring} = [")
            lines.extend(f"    {SafeText(e).quoted()}," for e in entries)
            lines.append("]")
        return lines

    def _entries(self, ring: str) -> list[str]:
        members = sorted(m for m in self._modules if self._rings.get(m) == ring)
        out: set[str] = set()
        covered: set[str] = set()
        for name in members:
            if name in covered:
                continue
            prefix = self._exact_prefix(name, ring)
            if prefix is None:
                out.add(glob.escape(name))
                continue
            under = self._under(prefix)
            covered.update(under)
            out.add(f"{glob.escape(prefix)}.*")
            if prefix in under:
                out.add(glob.escape(prefix))
        return sorted(out)

    def _exact_prefix(self, name: str, ring: str) -> str | None:
        parts = name.split(".")
        for end in range(2, len(parts) + 1):
            prefix = ".".join(parts[:end])
            under = self._under(prefix)
            if len(under) > 1 and all(self._rings.get(m) == ring for m in under):
                return prefix
        return None

    def _under(self, prefix: str) -> set[str]:
        return {m for m in self._modules if m == prefix or m.startswith(prefix + ".")}
