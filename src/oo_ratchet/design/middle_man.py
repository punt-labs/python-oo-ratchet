"""Single-call forwarding on one stored collaborator."""

from __future__ import annotations

import ast
from typing import Self

from .declaration import Declaration
from .project_types import ProjectTypes
from .shape import ClassShape, Method


class MiddleMan:
    """Require every public method to delegate, with explicit Protocol exemptions."""

    _owner: Declaration
    _types: ProjectTypes

    def __new__(cls, owner: Declaration, types: ProjectTypes) -> Self:
        self = super().__new__(cls)
        self._owner = owner
        self._types = types
        return self

    def found(self) -> bool:
        """Return whether this class is wholly a middle man."""
        methods = self._methods()
        fields = {self._delegate(m) for m in methods}
        return (
            len(methods) >= 2
            and len(fields) == 1
            and "" not in fields
            and not self._protocol()
        )

    def _methods(self) -> list[Method]:
        node = self._owner.node
        if not isinstance(node, ast.ClassDef):
            return []
        names = set(ClassShape(node).public_methods())
        return [
            n
            for n in node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name in names
            and not ClassShape._is_setter(n)
        ]

    def _protocol(self) -> bool:
        node = self._owner.node
        if not isinstance(node, ast.ClassDef):
            return False
        for base in node.bases:
            if ClassShape._name(base) == "Protocol":
                return True
            reference = base.value if isinstance(base, ast.Subscript) else base
            target = self._types.resolve(self._owner.module, reference)
            if target is not None and self._declares_protocol(target.node):
                return True
        return False

    @staticmethod
    def _declares_protocol(node: ast.AST) -> bool:
        return isinstance(node, ast.ClassDef) and any(
            ClassShape._name(base) == "Protocol" for base in node.bases
        )

    @classmethod
    def _delegate(cls, method: Method) -> str:
        body = cls._body(method)
        if len(body) != 1 or not isinstance(body[0], (ast.Return, ast.Expr)):
            return ""
        value = body[0].value
        if isinstance(value, ast.Await):
            value = value.value
        if isinstance(value, ast.Call):
            return cls._receiver(value)
        return ""

    @staticmethod
    def _body(method: Method) -> list[ast.stmt]:
        first = method.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            return method.body[1:]
        return method.body

    @classmethod
    def _receiver(cls, call: ast.Call) -> str:
        if sum(isinstance(n, ast.Call) for n in ast.walk(call)) != 1:
            return ""
        return cls._field(call.func)

    @staticmethod
    def _field(node: ast.expr) -> str:
        if not isinstance(node, ast.Attribute) or not isinstance(
            node.value, ast.Attribute
        ):
            return ""
        collaborator = node.value
        if isinstance(collaborator.value, ast.Name) and collaborator.value.id == "self":
            return collaborator.attr
        return ""
