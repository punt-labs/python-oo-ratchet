"""Literal and enum-member-form dispatch, without value or flow inference."""

from __future__ import annotations

import ast
from typing import Self

from oo_ratchet.core.domain.function_shape import FunctionShape


class TagSwitch:
    """Recognize three comparison arms on one syntactically identical reference."""

    _shape: FunctionShape

    def __new__(cls, shape: FunctionShape) -> Self:
        self = super().__new__(cls)
        self._shape = shape
        return self

    def found(self) -> bool:
        """Check only this function's body, not nested declarations."""
        return any(self._dispatch(n) for n in self._shape.nodes()) or any(
            self._guards(block) for block in self._shape.blocks()
        )

    @classmethod
    def _guards(cls, block: list[ast.stmt]) -> bool:
        return cls._run([cls._guard(statement) for statement in block])

    @staticmethod
    def _run(arms: list[set[str]]) -> bool:
        common: set[str] = set()
        count = 0
        for targets in arms:
            overlap = common & targets
            if overlap:
                common = overlap
                count += 1
            else:
                common = targets
                count = 1
            if count >= 3 and common:
                return True
        return False

    @classmethod
    def _guard(cls, node: ast.stmt) -> set[str]:
        if not isinstance(node, ast.If) or node.orelse:
            return set()
        if node.body and isinstance(node.body[-1], (ast.Return, ast.Raise)):
            return cls._comparison(node.test)
        return set()

    @classmethod
    def _dispatch(cls, node: ast.AST) -> bool:
        if isinstance(node, ast.If):
            return cls._chain(node)
        if isinstance(node, ast.Match):
            return (
                bool(cls._reference(node.subject))
                and sum(cls._pattern(case.pattern) for case in node.cases) >= 3
            )
        return False

    @classmethod
    def _chain(cls, node: ast.If) -> bool:
        arms = []
        current: ast.If | None = node
        while current is not None:
            arms.append(cls._comparison(current.test))
            tail = current.orelse
            current = (
                tail[0] if len(tail) == 1 and isinstance(tail[0], ast.If) else None
            )
        return cls._run(arms)

    @classmethod
    def _comparison(cls, node: ast.expr) -> set[str]:
        if not isinstance(node, ast.Compare) or len(node.ops) != 1:
            return set()
        if not isinstance(node.ops[0], ast.Eq):
            return set()
        left, right = node.left, node.comparators[0]
        return {
            reference
            for target, value in ((left, right), (right, left))
            if (reference := cls._reference(target)) and cls._literal(value)
        }

    @staticmethod
    def _reference(node: ast.expr) -> str:
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name):
            return ""
        return ".".join([node.id, *reversed(parts)])

    @classmethod
    def _literal(cls, node: ast.expr) -> bool:
        if isinstance(node, ast.Attribute):
            return bool(cls._reference(node))
        try:
            ast.literal_eval(node)
        except (ValueError, TypeError, SyntaxError):
            return False
        return True

    @classmethod
    def _pattern(cls, node: ast.pattern) -> bool:
        if isinstance(node, ast.MatchValue):
            return cls._literal(node.value)
        if isinstance(node, ast.MatchSingleton):
            return True
        return isinstance(node, ast.MatchOr) and all(
            cls._pattern(p) for p in node.patterns
        )
