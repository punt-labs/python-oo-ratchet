"""Follow a re-exported name through the package ``__init__`` files that bind it."""

from __future__ import annotations

import ast
from collections.abc import Callable, Mapping
from typing import Self

from oo_ratchet.core.domain.layer_violations import Site
from oo_ratchet.core.domain.modules import Module

from .exports import Origin, Reexports


class ExportChain:
    """Resolve ``from pkg import X`` to every module that can define ``X``.

    Each package ``__init__`` on the way may bind ``X`` to several origins (one
    per branch); every origin is followed, until no new origin appears, and each module
    reached is an edge the importer depends on.
    """

    _modules: Mapping[str, Module]
    _trees: dict[str, ast.Module]
    _rows: Callable[[Module], list[tuple[Site, str, str]]]

    def __new__(
        cls,
        modules: Mapping[str, Module],
        rows: Callable[[Module], list[tuple[Site, str, str]]],
    ) -> Self:
        self = super().__new__(cls)
        self._modules = modules
        self._rows = rows
        self._trees = {name: m.tree for name, m in modules.items()}
        return self

    def follow(self, target: str, symbol: str) -> list[str]:
        """Return the modules reached by following ``symbol`` out of ``target``."""
        reached: list[str] = []
        seen: set[Origin] = set()
        frontier = [(target, symbol)]
        while frontier:
            fresh = (
                origin
                for here, name in frontier
                for origin in self._origins(here, name)
                if origin[0] != here and origin not in seen
            )
            frontier = list(dict.fromkeys(fresh))
            seen.update(frontier)
            reached.extend(module for module, _ in frontier)
        return reached

    def _origins(self, target: str, symbol: str) -> frozenset[Origin]:
        module = self._modules.get(target)
        if module is None or not module.is_package:
            return frozenset()
        return Reexports(module.tree, self._rows(module), self._trees).get(symbol)
