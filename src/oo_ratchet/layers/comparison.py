"""Compare a scan with the layer config and the modules the base commit had."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from .widening import PolicyWidening

if TYPE_CHECKING:
    from collections.abc import Iterable

    from oo_ratchet.design.layer_config import LayerConfig
    from oo_ratchet.design.layer_edges import Edge

    from .scan import LayerScan


class BaseComparison:
    """What a scan changed against the base config, over the modules both share.

    A module absent at the base had no layer there, so it is neither judged
    under the base config nor counted as moved; its imports are still checked
    against the current config and the baseline.
    """

    _scan: LayerScan
    _base_config: LayerConfig
    _shared: frozenset[str]

    def __new__(
        cls, scan: LayerScan, base_config: LayerConfig, shared: Iterable[str]
    ) -> Self:
        self = super().__new__(cls)
        self._scan = scan
        self._base_config = base_config
        self._shared = frozenset(shared)
        return self

    def under_base(
        self, base_edges: frozenset[Edge] | None, accepted: frozenset[Edge]
    ) -> list[Edge]:
        """Return the shared modules' edges that violate under the base config."""
        if base_edges is None:
            return []
        held = self._scan.under(self._base_config).edges - base_edges - accepted
        return sorted(e for e in held if e.source in self._shared)

    def widened(self) -> list[str]:
        """Return the policy widenings against the base config."""
        return PolicyWidening.found(
            self._scan.config, self._base_config, sorted(self._shared)
        )
