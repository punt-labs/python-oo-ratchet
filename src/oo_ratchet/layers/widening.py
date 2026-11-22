"""Detect a layer policy that allows more imports than the base commit's did."""

from __future__ import annotations

from oo_ratchet.design.layer_config import LayerConfig


class PolicyWidening:
    """Compare two layer configs by which layers each layer may import."""

    @staticmethod
    def found(current: LayerConfig, base: LayerConfig) -> list[str]:
        """Return one line per layer whose permitted imports grew since ``base``."""
        was = {name: base.allowed(name) for name in base.layer_names()}
        found: list[str] = []
        for name in current.layer_names():
            extra = current.allowed(name) - was.get(name, frozenset({name}))
            if extra:
                names = ", ".join(sorted(extra))
                found.append(f"layer {name!r} may now import {names}")
        return found
