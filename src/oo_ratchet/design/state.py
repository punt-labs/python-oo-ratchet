"""Decide whether a class's instances carry data of their own."""

from __future__ import annotations

import ast
from typing import Self

type Method = ast.FunctionDef | ast.AsyncFunctionDef


class StateProbe:
    """Look for instance state in a class body and its methods.

    State is a non-``ClassVar`` annotated field in the class body, a non-empty
    ``__slots__``, or any write to an attribute of the instance: ``self.x =`` or
    ``self.__dict__[k] =`` in a method, the local a ``__new__`` constructor
    binds to ``super().__new__(cls)``, or a
    ``setattr``/``object.__setattr__`` call on it. Class-level constants are
    shared configuration, not state.
    """

    _found: bool

    def __new__(cls, node: ast.ClassDef, methods: tuple[Method, ...]) -> Self:
        self = super().__new__(cls)
        self._found = cls._body_declares(node) or cls.writes_any(methods)
        return self

    @property
    def found(self) -> bool:
        """Return whether the class holds instance state."""
        return self._found

    @classmethod
    def declares_slots(cls, node: ast.ClassDef) -> bool:
        """Return whether the class body declares a non-empty ``__slots__``."""
        return any(
            isinstance(item, ast.Assign) and cls._non_empty_slots(item)
            for item in node.body
        )

    @classmethod
    def writes_any(cls, methods: tuple[Method, ...]) -> bool:
        """Return whether any of ``methods`` writes an instance attribute."""
        return any(cls._writes_instance(m) for m in methods)

    @classmethod
    def _body_declares(cls, node: ast.ClassDef) -> bool:
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and not cls._is_classvar(
                item.annotation
            ):
                return True
            if isinstance(item, ast.Assign) and cls._non_empty_slots(item):
                return True
        return False

    @staticmethod
    def _is_classvar(annotation: ast.expr) -> bool:
        target = (
            annotation.value if isinstance(annotation, ast.Subscript) else annotation
        )
        if isinstance(target, ast.Name):
            return target.id in {"ClassVar", "Final"}
        return isinstance(target, ast.Attribute) and target.attr in {
            "ClassVar",
            "Final",
        }

    @staticmethod
    def _non_empty_slots(node: ast.Assign) -> bool:
        named = any(
            isinstance(t, ast.Name) and t.id == "__slots__" for t in node.targets
        )
        value = node.value
        empty = (isinstance(value, (ast.Tuple, ast.List)) and not value.elts) or (
            isinstance(value, ast.Constant) and value.value == ""
        )
        return named and not empty

    @classmethod
    def _writes_instance(cls, method: Method) -> bool:
        receiver = cls._receiver(method)
        if receiver is None:
            return False
        return any(cls._is_write(n, receiver) for n in cls._own_nodes(method))

    @classmethod
    def _receiver(cls, method: Method) -> str | None:
        if method.name == "__new__":
            return cls._allocated(method)
        if any(
            isinstance(d, ast.Name) and d.id in {"staticmethod", "classmethod"}
            for d in method.decorator_list
        ):
            return None
        args = method.args.posonlyargs + method.args.args
        return args[0].arg if args else None

    @staticmethod
    def _own_nodes(method: Method) -> list[ast.AST]:
        """Return the method's nodes, skipping nested defs with their own scope."""
        nested = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
        out: list[ast.AST] = []
        stack: list[ast.AST] = list(method.body)
        while stack:
            node = stack.pop()
            out.append(node)
            stack.extend(
                c for c in ast.iter_child_nodes(node) if not isinstance(c, nested)
            )
        return out

    @staticmethod
    def _allocated(method: Method) -> str:
        """Return the local a ``__new__`` binds to ``....__new__(cls)``."""
        for node in ast.walk(method):
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "__new__"
                and isinstance(node.targets[0], ast.Name)
            ):
                return node.targets[0].id
        return "self"

    @classmethod
    def _is_write(cls, node: ast.AST, receiver: str) -> bool:
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            return any(cls._is_own_attr(t, receiver) for t in targets)
        if isinstance(node, ast.Call):
            return cls._is_setattr(node, receiver)
        return False

    @staticmethod
    def _is_own_attr(target: ast.expr, receiver: str) -> bool:
        if isinstance(target, (ast.Tuple, ast.List)):
            return any(StateProbe._is_own_attr(t, receiver) for t in target.elts)
        if isinstance(target, ast.Subscript):
            return StateProbe._is_own_attr(target.value, receiver)
        return (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == receiver
        )

    @staticmethod
    def _is_setattr(node: ast.Call, receiver: str) -> bool:
        func = node.func
        first = node.args[0] if node.args else None
        if isinstance(func, ast.Name):
            named = func.id == "setattr"
            return named and isinstance(first, ast.Name) and first.id == receiver
        if not (isinstance(func, ast.Attribute) and func.attr == "__setattr__"):
            return False
        owner = func.value
        bound = (isinstance(owner, ast.Name) and owner.id == receiver) or (
            isinstance(owner, ast.Call)
            and isinstance(owner.func, ast.Name)
            and owner.func.id == "super"
        )
        return bound or (isinstance(first, ast.Name) and first.id == receiver)
