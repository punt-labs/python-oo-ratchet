"""The three permitted statement patterns for receiver types."""

from __future__ import annotations

import ast
from collections import Counter
from typing import Self

from .declaration import Declaration
from .function_shape import FunctionShape
from .project_types import ProjectTypes
from .receiver_bindings import ReceiverBindings


class ReceiverTypes:
    """Match annotations and single direct constructors; discard repeated writes."""

    _owner: Declaration
    _types: ProjectTypes
    _shape: FunctionShape

    def __new__(cls, owner: Declaration, types: ProjectTypes) -> Self:
        self = super().__new__(cls)
        self._owner = owner
        self._types = types
        self._shape = FunctionShape(owner)
        return self

    def known(self) -> dict[str, Declaration]:
        """Return explicit receiver types only, with no ordering or propagation."""
        writes = ReceiverBindings(self._owner).counts()
        candidates = self._candidates(writes)
        return {
            name: owner
            for name, owner in candidates.items()
            if owner is not None and writes[name] == 1
        }

    def _candidates(self, bindings: Counter[str]) -> dict[str, Declaration | None]:
        parameters = self._shape.parameters()
        candidates = {
            a.arg: self._types.resolve(self._owner.module, a.annotation)
            for a in parameters
        }
        for node in self._shape.nodes():
            candidate = self._statement(node, bindings)
            if candidate is not None:
                name, annotation = candidate
                candidates[name] = self._types.resolve(self._owner.module, annotation)
        return candidates

    @staticmethod
    def _statement(
        node: ast.AST, bindings: Counter[str]
    ) -> tuple[str, ast.expr] | None:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            return node.target.id, node.annotation
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            if (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and not bindings[node.value.func.id]
            ):
                return node.targets[0].id, node.value.func
        return None
