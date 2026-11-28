"""Package-level coupling metrics: fan-out, interface width, density, cohesion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from .graph import ImportGraph
from .packageinit import PackageInit


@dataclass(frozen=True, slots=True)
class PackageMetrics:
    """One sub-package's coupling profile."""

    package: str
    modules: int
    pkg_efferent_coupling: int
    pkg_interface_width: int
    pkg_intra_density: float
    pkg_cohesion: float

    def as_dict(self) -> dict[str, float | int | str]:
        """Return the metrics as a JSON-serializable row."""
        return {
            "package": self.package,
            "modules": self.modules,
            "pkg_efferent_coupling": self.pkg_efferent_coupling,
            "pkg_interface_width": self.pkg_interface_width,
            "pkg_intra_density": self.pkg_intra_density,
            "pkg_cohesion": self.pkg_cohesion,
        }


class PackageScorer:
    """Score each sub-package of a tree against the shared import graph."""

    _inits: tuple[PackageInit, ...]
    _graph: ImportGraph

    def __new__(cls, inits: tuple[PackageInit, ...], graph: ImportGraph) -> Self:
        self = super().__new__(cls)
        self._inits = inits
        self._graph = graph
        return self

    def score(self) -> list[PackageMetrics]:
        """Return metrics for every sub-package (dirs with ``__init__.py``)."""
        return [self._score_one(init) for init in self._inits]

    def _score_one(self, init: PackageInit) -> PackageMetrics:
        pkg_name = init.name
        keys = self._module_keys(pkg_name)
        return PackageMetrics(
            package=pkg_name,
            modules=len(keys),
            pkg_efferent_coupling=self._efferent(pkg_name, keys),
            pkg_interface_width=init.interface_width(),
            pkg_intra_density=self._intra_density(keys, pkg_name),
            pkg_cohesion=self._cohesion(keys),
        )

    def _module_keys(self, pkg_name: str) -> set[str]:
        prefix = f"{pkg_name}."
        return {k for k in self._graph.edges if k == pkg_name or k.startswith(prefix)}

    def _efferent(self, pkg_name: str, keys: set[str]) -> int:
        siblings: set[str] = set()
        prefix = f"{pkg_name}."
        depth = pkg_name.count(".") + 1
        for key in keys:
            for dep in self._graph.neighbors(key):
                if dep == pkg_name or dep.startswith(prefix) or dep in keys:
                    continue
                siblings.add(".".join(dep.split(".")[:depth]))
        return len(siblings)

    def _intra_density(self, keys: set[str], pkg_name: str) -> float:
        intra = sum(
            1
            for key in keys
            for dep in self._graph.neighbors(key)
            if dep in keys or dep == pkg_name
        )
        n = len(keys)
        max_edges = n * (n - 1) if n > 1 else 1
        return round(intra / max_edges, 3) if max_edges > 0 else 0.0

    def _cohesion(self, keys: set[str]) -> float:
        n = len(keys)
        if n == 0:
            return 0.0
        with_dep = sum(
            1
            for key in keys
            if any(dep in keys and dep != key for dep in self._graph.neighbors(key))
        )
        return round(with_dep / n, 3)
