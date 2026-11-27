"""Coupling and cohesion metrics for a single parsed Python module."""

from __future__ import annotations

import ast
from itertools import combinations
from typing import Self

from .class_state import ClassState
from .imports import ImportResolver

_TYPE_BASES = frozenset({"Protocol", "TypedDict", "BaseModel"})


class ModuleCouplingMetrics:
    """Compute one module's efferent coupling, interface width, and LCOM.

    ``circular_imports`` is left at 0 here and filled in by the scorer once the
    whole-package import graph is known -- a single module cannot see a cycle it
    only participates in.
    """

    _path: str
    _tree: ast.Module
    _resolver: ImportResolver
    _stateless_values: str

    def __new__(
        cls,
        path: str,
        tree: ast.Module,
        resolver: ImportResolver,
        stateless_values: str = "dataclass",
    ) -> Self:
        self = super().__new__(cls)
        self._path = path
        self._tree = tree
        self._resolver = resolver
        self._stateless_values = stateless_values
        return self

    def compute(self) -> dict[str, float | int | str]:
        """Return every per-module metric as a JSON-serializable dict."""
        lcom_values = self._lcom_values()
        return {
            "file": self._path,
            "efferent_coupling": len(self._resolver.internal_imports(self._tree)),
            "public_names": self._public_names(),
            "circular_imports": 0,  # filled by the scorer after graph analysis
            "max_lcom": max(lcom_values) if lcom_values else 0.0,
            "avg_lcom": (
                round(sum(lcom_values) / len(lcom_values), 3) if lcom_values else 0.0
            ),
        }

    # ---- public interface width ----

    def _public_names(self) -> int:
        explicit = self._all_count()
        return explicit if explicit is not None else self._heuristic_count()

    def _all_count(self) -> int | None:
        """Return ``len(__all__)`` if the module declares it, else ``None``."""
        for node in ast.iter_child_nodes(self._tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "__all__"
                    and isinstance(node.value, (ast.List, ast.Tuple))
                ):
                    return len(node.value.elts)
        return None

    def _heuristic_count(self) -> int:
        return sum(
            self._node_public_names(node) for node in ast.iter_child_nodes(self._tree)
        )

    @staticmethod
    def _node_public_names(node: ast.AST) -> int:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            return 0 if node.name.startswith("_") else 1
        if isinstance(node, ast.Assign):
            return sum(
                1
                for t in node.targets
                if isinstance(t, ast.Name) and not t.id.startswith("_")
            )
        return 0

    # ---- LCOM cohesion ----

    def _lcom_values(self) -> list[float]:
        values: list[float] = []
        for node in ast.iter_child_nodes(self._tree):
            if not isinstance(node, ast.ClassDef) or self._is_exempt(node):
                continue
            lcom = self._class_lcom(node)
            if lcom is not None:
                values.append(lcom)
        return values

    def _class_lcom(self, cls_node: ast.ClassDef) -> float | None:
        """Return the class's LCOM, or ``None`` when it has < 2 instance methods."""
        methods = self._instance_method_attrs(cls_node)
        if len(methods) <= 1:
            return None
        return self._lcom_from(methods)

    def _instance_method_attrs(self, cls_node: ast.ClassDef) -> list[set[str]]:
        methods: list[set[str]] = []
        for item in ast.iter_child_nodes(cls_node):
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if self._is_static_or_class(item):
                continue
            methods.append(self._method_self_attrs(item))
        return methods

    @staticmethod
    def _is_static_or_class(item: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        marks = {"staticmethod", "classmethod"}
        for dec in item.decorator_list:
            if isinstance(dec, ast.Name) and dec.id in marks:
                return True
            if isinstance(dec, ast.Attribute) and dec.attr in marks:
                return True
        return False

    @staticmethod
    def _method_self_attrs(method: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
        # LCOM measures DATA cohesion -- fields shared between methods. Count
        # every ``self.<name>`` field read/write, public or private (an
        # underscore-only filter under-reads frozen dataclass value objects
        # whose fields are public by contract, PY-CC-6), but exclude
        # ``self.helper()`` call targets: sharing a helper method is method
        # dispatch, not shared state.
        call_targets = {
            node.func
            for node in ast.walk(method)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        return {
            node.attr
            for node in ast.walk(method)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
            and node not in call_targets
        }

    @staticmethod
    def _lcom_from(methods: list[set[str]]) -> float:
        total = 0
        disjoint = 0
        for m1, m2 in combinations(methods, 2):
            total += 1
            if not m1 & m2:
                disjoint += 1
        return round(disjoint / total, 3) if total else 0.0

    def _is_exempt(self, node: ast.ClassDef) -> bool:
        """Return True for data shapes and stateless values, which LCOM cannot see.

        The default exempts value shapes that store no instance state;
        ``stateless_values == "any"`` also exempts every class that stores no
        private ``self._*`` state, so it is a superset of the default.
        """
        if self._is_type_definition(node):
            return True
        if self._declares_value_shape(node) and ClassState(node).stores_nothing():
            return True
        return self._stateless_values == "any" and ClassState(node).stores_none()

    @classmethod
    def _declares_value_shape(cls, node: ast.ClassDef) -> bool:
        """Return True for a ``@dataclass`` or an empty-``__slots__`` marker class."""
        return any(map(cls._is_dataclass, node.decorator_list)) or any(
            map(cls._is_empty_slots, node.body)
        )

    @staticmethod
    def _is_dataclass(deco: ast.expr) -> bool:
        target = deco.func if isinstance(deco, ast.Call) else deco
        if isinstance(target, ast.Name):
            return target.id == "dataclass"
        return isinstance(target, ast.Attribute) and target.attr == "dataclass"

    @staticmethod
    def _is_empty_slots(item: ast.stmt) -> bool:
        return (
            isinstance(item, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "__slots__" for t in item.targets
            )
            and isinstance(item.value, ast.Tuple)
            and not item.value.elts
        )

    @staticmethod
    def _is_type_definition(node: ast.ClassDef) -> bool:
        """Return True for Protocol/TypedDict/BaseModel classes (excluded from LCOM)."""
        for base in node.bases:
            target = base.value if isinstance(base, ast.Subscript) else base
            if isinstance(target, ast.Name) and target.id in _TYPE_BASES:
                return True
        return False
