"""Direct names in annotations, with quoted spellings parsed as syntax."""

from __future__ import annotations

import ast


def type_name(node: ast.expr | None) -> str:
    """Return a dotted name, or "" for anything that is not a direct reference.

    Calls, containers and arbitrary expressions are never turned into class
    types; a quoted spelling is parsed as an expression and read the same way.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{type_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Constant):
        return _quoted(node.value)
    return ""


def _quoted(value: object) -> str:
    if not isinstance(value, str):
        return ""
    try:
        return type_name(ast.parse(value, mode="eval").body)
    except SyntaxError:
        return ""
