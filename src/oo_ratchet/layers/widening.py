"""Detect a layer policy that allows more imports than the base commit's did."""

from __future__ import annotations

from oo_ratchet.design.layer_config import LayerConfig


class PolicyWidening:
    """Compare two layer configs by which layers each layer may import."""

    @staticmethod
    def found(current: LayerConfig, base: LayerConfig) -> list[str]:
        """Return one line per layer whose permitted imports grew since ``base``."""
        was = PolicyWidening._permissions(base)
        found: list[str] = []
        for name, allowed in PolicyWidening._permissions(current).items():
            extra = allowed - was.get(name, frozenset({name}))
            if extra:
                names = ", ".join(sorted(extra))
                found.append(f"layer {name!r} may now import {names}")
        return found

    @staticmethod
    def _permissions(config: LayerConfig) -> dict[str, frozenset[str]]:
        """Map each active layer to the active layers it may import."""
        active = set(config.layer_names())
        return {name: config.allowed(name) & active for name in active}
