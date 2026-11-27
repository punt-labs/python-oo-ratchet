"""What the layers gate reports about a whole package, from its edge extractor."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from .module_violations import ModuleViolations

if TYPE_CHECKING:
    from oo_ratchet.core.domain.layer_config import LayerConfig
    from oo_ratchet.core.domain.layer_edges import Violation
    from oo_ratchet.core.domain.modules import ModuleIndex

    from .strict import StrictViolations


class PackageEdges:
    """The refused edges, unplaced modules and unresolvable imports of a package."""

    _found: StrictViolations
    _index: ModuleIndex
    _config: LayerConfig

    def __new__(
        cls, found: StrictViolations, index: ModuleIndex, config: LayerConfig
    ) -> Self:
        self = super().__new__(cls)
        self._found = found
        self._index = index
        self._config = config
        return self

    def violations(self) -> list[Violation]:
        """Return every refused edge, one per source and target module."""
        per_module = ModuleViolations(
            self._found, self._config, self._index.package_name
        )
        return sorted(set().union(*(per_module.of(m) for m in self._index.modules())))

    def unassigned(self) -> list[str]:
        """Return the non-root modules that match no layer."""
        names = (self._found.name(m) for m in self._index.modules())
        return sorted(n for n in names if "." in n and self._config.layer(n) is None)

    def unresolvable(self) -> list[str]:
        """Return ``path:line`` for each relative import that climbs past the root."""
        found: list[str] = []
        for module in self._index.modules():
            parts = self._found.name(module).split(".")
            depth = len(parts) if module.is_package else len(parts) - 1
            found.extend(
                f"{module.path}:{node.lineno}"
                for node in module.import_froms()
                if node.level > depth
            )
        return sorted(found)
