"""The three permitted statement patterns for receiver types."""

from __future__ import annotations

import ast
from collections import Counter
from typing import Self

from .declaration import Declaration
from .function_shape import FunctionShape
from .project_types import ProjectTypes


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
        writes = self._writes()
        candidates = self._candidates()
        return {
            name: owner
            for name, owner in candidates.items()
            if owner is not None and writes[name] == 1
        }

    def _writes(self) -> Counter[str]:
        parameters = self._shape.parameters()
        writes = Counter(a.arg for a in parameters)
        writes.update(
            n.id
            for n in self._shape.nodes()
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
        )
        return writes

    def _candidates(self) -> dict[str, Declaration | None]:
        parameters = self._shape.parameters()
        candidates = {
            a.arg: self._types.resolve(self._owner.module, a.annotation)
            for a in parameters
        }
        for node in self._shape.nodes():
            candidate = self._statement(node)
            if candidate is not None:
                name, annotation = candidate
                candidates[name] = self._types.resolve(self._owner.module, annotation)
        return candidates

    @staticmethod
    def _statement(node: ast.AST) -> tuple[str, ast.expr] | None:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            return node.target.id, node.annotation
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            if isinstance(node.value, ast.Call) and isinstance(
                node.value.func, ast.Name
            ):
                return node.targets[0].id, node.value.func
        return None
