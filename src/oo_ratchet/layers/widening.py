"""Detect a layer policy that allows more than the base commit's did."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Self

from oo_ratchet.design.layer_config import LayerConfig


class PolicyWidening:
    """Compare two layer configs by which layers each layer may import."""

    @staticmethod
    def found(
        current: LayerConfig, base: LayerConfig, modules: Iterable[str] = ()
    ) -> list[str]:
        """Return a line per layer whose imports grew or module that moved outward."""
        found = PolicyWidening._imports(current, base)
        return found + _ModuleMoves(current, base).lines(modules)

    @staticmethod
    def _imports(current: LayerConfig, base: LayerConfig) -> list[str]:
        """Return one line per layer whose permitted imports grew since ``base``."""
        was = PolicyWidening._permissions(base)
        lines = (
            PolicyWidening._grown(name, allowed, was.get(name, frozenset({name})))
            for name, allowed in PolicyWidening._permissions(current).items()
        )
        return list(filter(None, lines))

    @staticmethod
    def _grown(name: str, allowed: frozenset[str], was: frozenset[str]) -> str:
        """Return the line for a layer that gained imports, or ``""``."""
        extra = allowed - was
        if not extra:
            return ""
        return f"layer {name!r} may now import {', '.join(sorted(extra))}"

    @staticmethod
    def _permissions(config: LayerConfig) -> dict[str, frozenset[str]]:
        """Map each active layer to the active layers it may import."""
        active = set(config.layer_names())
        return {name: config.allowed(name) & active for name in active}


class _ModuleMoves:
    """Modules assigned to an outer ring (or out of ``domain``) than at the base.

    Only the fixed four-ring form has a ring order; with a declared config on
    either side nothing is compared.
    """

    _current: LayerConfig
    _base: LayerConfig

    def __new__(cls, current: LayerConfig, base: LayerConfig) -> Self:
        self = super().__new__(cls)
        self._current = current
        self._base = base
        return self

    def lines(self, modules: Iterable[str]) -> list[str]:
        """Return one line per scanned module that moved outward."""
        if not all((self._current.ORDERED, self._base.ORDERED)):
            return []
        return list(filter(None, map(self._line, modules)))

    def _line(self, module: str) -> str:
        """Return the description of a move, or ``""`` when ``module`` stayed."""
        was, now = self._base.layer(module), self._current.layer(module)
        if not self._outward(was, now):
            return ""
        return f"module {module!r} moved from layer {was!r} to {now!r}"

    def _outward(self, was: str | None, now: str | None) -> bool:
        if None in (was, now):
            return False
        order = self._current.ORDER
        return order.index(now) < order.index(was)
