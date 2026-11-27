"""How a layer policy allows more than the base commit's policy did."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Self

from oo_ratchet.core.domain.layer_config import LayerConfig


class LayerWidening:
    """The current layer config measured against the base commit's.

    A layer widened when it may import more active layers than at the base; a
    module moved outward when it is assigned to an outer ring, or to no layer.
    Only the layers that match modules are compared, and ring moves exist only
    when both sides are the fixed four-ring form, the one with a ring order.
    """

    _current: LayerConfig
    _base: LayerConfig

    def __new__(cls, current: LayerConfig, base: LayerConfig) -> Self:
        self = super().__new__(cls)
        self._current = current
        self._base = base
        return self

    def lines(self, modules: Iterable[str] = ()) -> list[str]:
        """Return a line per layer whose imports grew or module that moved outward."""
        return self._imports() + self._moves(modules)

    def _imports(self) -> list[str]:
        """Return one line per layer whose permitted imports grew since the base."""
        was = self._permissions(self._base)
        lines = (
            self._grown(name, allowed, was.get(name, frozenset({name})))
            for name, allowed in self._permissions(self._current).items()
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

    def _moves(self, modules: Iterable[str]) -> list[str]:
        """Return one line per scanned module that moved outward."""
        if not all((self._current.ORDERED, self._base.ORDERED)):
            return []
        return list(filter(None, map(self._move, modules)))

    def _move(self, module: str) -> str:
        """Return the description of a move, or ``""`` when ``module`` stayed."""
        was, now = self._base.layer(module), self._current.layer(module)
        if self._rank(now) >= self._rank(was):
            return ""
        return f"module {module!r} moved from layer {was!r} to {self._label(now)}"

    def _rank(self, layer: str | None) -> int:
        """Return the ring index of ``layer``; no layer ranks outside every ring."""
        return -1 if layer is None else self._current.ORDER.index(layer)

    @staticmethod
    def _label(layer: str | None) -> str:
        return "no layer" if layer is None else repr(layer)
