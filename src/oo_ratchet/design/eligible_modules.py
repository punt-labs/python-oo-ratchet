"""Which modules the data rules may report on: those outside the mapped edges."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from oo_ratchet.core.domain.layer_imports import LayerImports

if TYPE_CHECKING:
    from oo_ratchet.core.domain.declaration import Declaration
    from oo_ratchet.core.domain.layer_config import LayerConfig
    from oo_ratchet.core.domain.modules import ModuleIndex


class EligibleModules:
    """Keep the keys of the modules that sit outside the entry and adapter layers."""

    _keys: frozenset[str]

    def __new__(cls, index: ModuleIndex, config: LayerConfig | None) -> Self:
        self = super().__new__(cls)
        names = LayerImports(index)
        self._keys = frozenset(
            m.key
            for m in index.modules()
            if config is None
            or config.layer(names.canonical_name(m)) not in {"entry", "adapters"}
        )
        return self

    def holds(self, owner: Declaration) -> bool:
        """Return whether this declaration is outside explicitly mapped edges."""
        return owner.module.key in self._keys
