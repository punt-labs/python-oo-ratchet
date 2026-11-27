"""Detect whether a class body writes private (``self._x``) instance state.

Backs the coupling gate's ``stateless-values = "any"`` LCOM exemption: a class
that never writes private state carries no instance cohesion to measure.
"""

from __future__ import annotations

import ast
from typing import Self

_MUTATORS = frozenset(
    {
        "add",
        "append",
        "appendleft",
        "clear",
        "discard",
        "extend",
        "insert",
        "pop",
        "popitem",
        "remove",
        "setdefault",
        "sort",
        "update",
    }
)


class ClassState:
    """The instance-state writes of one class body, read from its AST."""

    _node: ast.ClassDef
    _nodes: list[ast.AST]

    def __new__(cls, node: ast.ClassDef) -> Self:
        self = super().__new__(cls)
        self._node = node
        self._nodes = self._own_nodes(node)
        return self

    def stores_none(self) -> bool:
        """Return True when the class never writes a private ``self._*`` attr.

        A write through ``object``/``super()``/``type(self)`` ``.__setattr__``
        (the frozen-class idiom) counts as a store too (lux #498).
        """
        return not any(self._writes_private_state(n) for n in self._nodes)

    def stores_nothing(self) -> bool:
        """Return True when the class never stores instance state in its own AST.

        Applied only to a marker (``__slots__ = ()``) or a ``@dataclass``, whose
        fields the generated ``__init__`` sets; either reads as LCOM 1.0 otherwise. A
        ``object.__setattr__(self, ...)`` call counts as a store (lux #498).
        """
        return not any(self._stores_self(sub) for sub in self._nodes)

    @staticmethod
    def _own_nodes(node: ast.ClassDef) -> list[ast.AST]:
        """Return the class's AST nodes, not descending into nested classes."""
        out: list[ast.AST] = []
        stack: list[ast.AST] = list(node.body)
        while stack:
            sub = stack.pop()
            out.append(sub)
            if not isinstance(sub, ast.ClassDef):
                stack.extend(ast.iter_child_nodes(sub))
        return out

    @classmethod
    def _writes_private_state(cls, sub: ast.AST) -> bool:
        if isinstance(sub, ast.Call):
            return cls._is_private_setattr(sub) or cls._mutates_private(sub)
        if isinstance(sub, ast.Subscript):
            return cls._is_private_dict_store(sub) or (
                not isinstance(sub.ctx, ast.Load) and cls._is_private_attr(sub.value)
            )
        return (
            isinstance(sub, ast.Attribute)
            and isinstance(sub.ctx, ast.Store)
            and cls._is_self(sub.value)
            and sub.attr.startswith("_")
        )

    @classmethod
    def _is_private_dict_store(cls, sub: ast.Subscript) -> bool:
        """Return True for ``self.__dict__["_x"] = ...``."""
        owner = sub.value
        return (
            isinstance(sub.ctx, ast.Store)
            and isinstance(owner, ast.Attribute)
            and owner.attr == "__dict__"
            and cls._is_self(owner.value)
            and cls._is_private_name(sub.slice)
        )

    @classmethod
    def _mutates_private(cls, call: ast.Call) -> bool:
        """Return True for ``self._x.append(...)`` and other in-place mutators."""
        func = call.func
        return (
            isinstance(func, ast.Attribute)
            and func.attr in _MUTATORS
            and (
                cls._is_private_attr(func.value)
                or (cls._is_self_dict(func.value) and cls._has_private_key(call))
            )
        )

    @classmethod
    def _is_self_dict(cls, node: ast.expr) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "__dict__"
            and cls._is_self(node.value)
        )

    @classmethod
    def _has_private_key(cls, call: ast.Call) -> bool:
        """Return True when a ``self.__dict__`` mutator may touch a ``_x`` key."""
        if any(kw.arg is None or kw.arg.startswith("_") for kw in call.keywords):
            return True
        return any(cls._may_be_private_key(arg) for arg in call.args[:1])

    @classmethod
    def _may_be_private_key(cls, arg: ast.expr) -> bool:
        if isinstance(arg, ast.Constant):
            return cls._is_private_name(arg)
        if isinstance(arg, ast.Dict):
            return any(k is None or cls._is_private_name(k) for k in arg.keys)
        return True

    @classmethod
    def _is_private_attr(cls, node: ast.expr) -> bool:
        """Return True for ``self._x``, also through ``[k]`` (``self._x[k][j]``)."""
        while isinstance(node, ast.Subscript):
            if cls._is_self_dict(node.value):
                return cls._is_private_name(node.slice)
            node = node.value
        return (
            isinstance(node, ast.Attribute)
            and cls._is_self(node.value)
            and node.attr.startswith("_")
            and not node.attr.endswith("__")
        )

    @staticmethod
    def _is_self(node: ast.expr) -> bool:
        return isinstance(node, ast.Name) and node.id == "self"

    @staticmethod
    def _is_private_name(node: ast.expr) -> bool:
        return isinstance(node, ast.Constant) and str(node.value).startswith("_")

    @classmethod
    def _is_private_setattr(cls, call: ast.Call) -> bool:
        """Return True for a ``setattr``/``__setattr__`` write of a ``_x`` attr.

        Unbound forms (``setattr(self, ...)``, ``object``/``type(self)``
        ``.__setattr__(self, ...)``) take ``self`` first; bound forms
        (``super()``/``self`` ``.__setattr__("_x", v)``) take the name first.
        """
        func = call.func
        if isinstance(func, ast.Name):
            return func.id == "setattr" and cls._self_private_args(call.args)
        if not isinstance(func, ast.Attribute) or func.attr != "__setattr__":
            return False
        if cls._is_bound_receiver(func.value):
            return bool(call.args) and cls._is_private_name(call.args[0])
        return cls._is_unbound_receiver(func.value) and cls._self_private_args(
            call.args
        )

    @classmethod
    def _self_private_args(cls, args: list[ast.expr]) -> bool:
        return (
            len(args) >= 2 and cls._is_self(args[0]) and cls._is_private_name(args[1])
        )

    @classmethod
    def _is_bound_receiver(cls, receiver: ast.expr) -> bool:
        """Return True for ``self`` or ``super()``."""
        return cls._is_self(receiver) or cls._is_call_to(receiver, "super")

    @classmethod
    def _is_unbound_receiver(cls, receiver: ast.expr) -> bool:
        """Return True for ``object`` or ``type(...)``."""
        is_object = isinstance(receiver, ast.Name) and receiver.id == "object"
        return is_object or cls._is_call_to(receiver, "type")

    @staticmethod
    def _is_call_to(node: ast.expr, name: str) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        )

    @classmethod
    def _stores_self(cls, sub: ast.AST) -> bool:
        """Return True for an instance store: attribute, setattr or ``__dict__``."""
        if isinstance(sub, ast.Attribute):
            return isinstance(sub.ctx, ast.Store) and cls._is_self(sub.value)
        if isinstance(sub, ast.Subscript):
            return isinstance(sub.ctx, ast.Store) and cls._is_self_dict(sub.value)
        return isinstance(sub, ast.Call) and cls._sets_self_attr(sub)

    @classmethod
    def _sets_self_attr(cls, call: ast.Call) -> bool:
        func = call.func
        if isinstance(func, ast.Name):
            return (
                func.id == "setattr" and bool(call.args) and cls._is_self(call.args[0])
            )
        if not isinstance(func, ast.Attribute):
            return False
        if func.attr in _MUTATORS and cls._is_self_dict(func.value):
            return True
        if func.attr != "__setattr__":
            return False
        return cls._is_bound_receiver(func.value) or (
            bool(call.args) and cls._is_self(call.args[0])
        )
