"""Declared fields and public behavior of syntactic project classes."""

from __future__ import annotations

import ast
from typing import Self, cast

from .declaration import Declaration
from .function_shape import FunctionShape
from .shape import ClassShape
from .state import StateProbe
from .wrapper import ValueWrapper


class DataFields:
    """Collect annotations, literal slots and direct instance-field writes."""

    _node: ast.ClassDef
    _owner: Declaration

    def __new__(cls, owner: Declaration) -> Self:
        self = super().__new__(cls)
        self._owner = owner
        self._node = cast("ast.ClassDef", owner.node)
        return self

    def names(self) -> frozenset[str]:
        """Return concrete field names, excluding ClassVar and Final constants."""
        return frozenset(
            self._annotations()
            | set(ValueWrapper._slot_names(self._node) or ())
            | self._attrs_fields()
            | self._instance_fields()
        )

    def _annotations(self) -> set[str]:
        return {
            n.target.id
            for n in self._node.body
            if isinstance(n, ast.AnnAssign)
            and isinstance(n.target, ast.Name)
            and not StateProbe._is_classvar(n.annotation)
        }

    def _instance_fields(self) -> set[str]:
        methods = [
            n
            for n in self._node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        nodes = [
            n
            for method in methods
            for n in FunctionShape(
                Declaration(self._owner.module, method, method.name, "method")
            ).nodes()
        ]
        return {
            n.attr
            for n in nodes
            if isinstance(n, ast.Attribute)
            and isinstance(n.ctx, ast.Store)
            and isinstance(n.value, ast.Name)
            and n.value.id == "self"
        }

    def data_only(self) -> bool:
        """Return whether a data declaration exposes no public behavior."""
        return self._data_declaration() and not any(
            self._public_behavior(n) for n in self._node.body
        )

    @staticmethod
    def _public_behavior(node: ast.stmt) -> bool:
        return (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and (not node.name.startswith("_") or node.name == "__call__")
            and not ClassShape._is_property(node)
            and not ClassShape._is_setter(node)
        )

    def _data_declaration(self) -> bool:
        marked = any(
            ClassShape._name(d) in {"dataclass", "define", "frozen", "attrs", "s"}
            for d in self._node.decorator_list
        )
        named = any(ClassShape._name(b) == "NamedTuple" for b in self._node.bases)
        return bool(marked or named or StateProbe.declares_slots(self._node))

    def _attrs_fields(self) -> set[str]:
        return {
            target.id
            for n in self._node.body
            if isinstance(n, ast.Assign)
            and isinstance(n.value, ast.Call)
            and ClassShape._name(n.value.func) in {"field", "ib", "attrib"}
            for target in n.targets
            if isinstance(target, ast.Name)
        }
