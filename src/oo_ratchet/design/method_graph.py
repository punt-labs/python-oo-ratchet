"""LCOM4 components of instance methods, excluding initialization hooks."""

from __future__ import annotations

import ast
from itertools import combinations
from typing import Self

from oo_ratchet.coupling.metrics import ModuleCouplingMetrics

from .declaration import Declaration
from .function_shape import FunctionShape
from .shape import ClassShape, Method

type _Footprint = tuple[str, set[str], set[str]]


class MethodGraph:
    """Join methods through shared self fields or direct calls to each other."""

    _owner: Declaration

    def __new__(cls, owner: Declaration) -> Self:
        self = super().__new__(cls)
        self._owner = owner
        return self

    def components(self) -> int:
        """Return one for classes below the three-method applicability threshold."""
        methods = self._methods(self._owner)
        if len(methods) < 3:
            return 1
        names = {n.name for n in self._members(self._owner)}
        return self._count([self._footprint(m, names) for m in methods])

    @classmethod
    def _methods(cls, owner: Declaration) -> list[Declaration]:
        return [
            Declaration(owner.module, n, f"{owner.symbol}.{n.name}", "method")
            for n in cls._members(owner)
            if n.name not in {"__init__", "__new__", "__post_init__"}
            and not ModuleCouplingMetrics._is_static_or_class(n)
        ]

    @staticmethod
    def _members(owner: Declaration) -> list[Method]:
        node = owner.node
        if not isinstance(node, ast.ClassDef):
            return []
        return [
            n
            for n in node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not ClassShape._is_property(n)
            and not ClassShape._is_setter(n)
        ]

    @classmethod
    def _footprint(cls, owner: Declaration, methods: set[str]) -> _Footprint:
        nodes = FunctionShape(owner).nodes()
        targets = {n.func for n in nodes if isinstance(n, ast.Call)}
        attrs = cls._attributes(nodes)
        return (
            owner.node.name,
            {n.attr for n in attrs if n not in targets or n.attr not in methods},
            {n.attr for n in attrs if n in targets and n.attr in methods},
        )

    @staticmethod
    def _attributes(nodes: list[ast.AST]) -> set[ast.Attribute]:
        return {
            n
            for n in nodes
            if isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name)
            and n.value.id == "self"
        }

    @classmethod
    def _count(cls, footprints: list[_Footprint]) -> int:
        parents = list(range(len(footprints)))
        for i, j in combinations(range(len(footprints)), 2):
            if cls._connected(footprints[i], footprints[j]):
                parents[cls._root(parents, j)] = cls._root(parents, i)
        return len({cls._root(parents, i) for i in range(len(parents))})

    @staticmethod
    def _connected(left: _Footprint, right: _Footprint) -> bool:
        return bool(left[1] & right[1]) or left[0] in right[2] or right[0] in left[2]

    @staticmethod
    def _root(parents: list[int], index: int) -> int:
        while parents[index] != index:
            index = parents[index]
        return index
