"""Recognize slotted classes that only wrap plain data."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, ClassVar, Self

from .state import StateProbe

if TYPE_CHECKING:
    from .state import Method


class ValueWrapper:
    """Decide whether a class is an immutable wrapper around plain data.

    That means non-empty ``__slots__``, every field annotated in the body with
    builtin data types only (``dict[str, object]``, ``str``, ``int | None``),
    and fields written only by ``__new__``/``__init__``. ``JsonObject`` is
    one; a class holding a ``Path``, a client or any other collaborator is
    not, since importing it couples the caller to that behavior.
    """

    _DATA_TYPES: ClassVar[frozenset[str]] = frozenset(
        {
            "str", "int", "float", "bool", "bytes", "complex", "object", "None",
            "dict", "list", "tuple", "set", "frozenset", "Mapping", "Sequence",
            "Literal", "Optional", "Union", "Final", "Any",
        }
    )  # fmt: skip
    _CONSTRUCTORS: ClassVar[frozenset[str]] = frozenset({"__new__", "__init__"})

    _found: bool

    def __new__(cls, node: ast.ClassDef, methods: tuple[Method, ...]) -> Self:
        self = super().__new__(cls)
        mutators = tuple(m for m in methods if m.name not in cls._CONSTRUCTORS)
        self._found = (
            StateProbe.declares_slots(node)
            and cls._plain_fields(node)
            and not StateProbe.writes_any(mutators)
        )
        return self

    @property
    def found(self) -> bool:
        """Return whether the class is a plain-data value wrapper."""
        return self._found

    @classmethod
    def _plain_fields(cls, node: ast.ClassDef) -> bool:
        fields = {
            item.target.id: item.annotation
            for item in node.body
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
        }
        slots = cls._slot_names(node)
        return (
            slots is not None
            and slots <= fields.keys()
            and all(cls._names(a) <= cls._DATA_TYPES for a in fields.values())
        )

    @staticmethod
    def _slot_names(node: ast.ClassDef) -> set[str] | None:
        """Return the literal ``__slots__`` names, or None if not literal."""
        for item in node.body:
            if not (
                isinstance(item, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == "__slots__"
                    for t in item.targets
                )
            ):
                continue
            value = item.value
            elts = value.elts if isinstance(value, (ast.Tuple, ast.List)) else [value]
            if not all(
                isinstance(e, ast.Constant) and isinstance(e.value, str) for e in elts
            ):
                return None
            return {str(e.value) for e in elts if isinstance(e, ast.Constant)}
        return None

    @classmethod
    def _names(cls, node: ast.expr) -> set[str]:
        """Return the type names in an annotation, quoted parts included."""
        if isinstance(node, ast.Constant):
            return cls._constant_names(node.value)
        if isinstance(node, ast.Name):
            return {node.id}
        if isinstance(node, ast.Attribute):
            return {node.attr}
        if isinstance(node, ast.Subscript) and cls._names(node.value) == {"Literal"}:
            return {"Literal"}
        names: set[str] = set()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                names |= cls._names(child)
        return names

    @classmethod
    def _constant_names(cls, value: object) -> set[str]:
        if value is None:
            return {"None"}
        if not isinstance(value, str):
            return set()
        try:
            return cls._names(ast.parse(value, mode="eval").body)
        except SyntaxError:
            return {value}
