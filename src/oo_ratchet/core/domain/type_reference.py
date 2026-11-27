"""Direct names in annotations, with quoted spellings parsed as syntax."""

from __future__ import annotations

import ast


class TypeReference:
    """Do not turn calls, containers, or arbitrary expressions into class types."""

    @classmethod
    def name(cls, node: ast.expr | None) -> str:
        """Return a dotted name or an empty unsupported reference."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{cls.name(node.value)}.{node.attr}"
        if isinstance(node, ast.Constant):
            return cls._quoted(node.value)
        return ""

    @classmethod
    def _quoted(cls, value: object) -> str:
        if not isinstance(value, str):
            return ""
        try:
            return cls.name(ast.parse(value, mode="eval").body)
        except SyntaxError:
            return ""
