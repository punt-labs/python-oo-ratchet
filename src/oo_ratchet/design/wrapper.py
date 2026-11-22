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
        fields = [
            item.annotation for item in node.body if isinstance(item, ast.AnnAssign)
        ]
        return bool(fields) and all(cls._names(a) <= cls._DATA_TYPES for a in fields)

    @staticmethod
    def _names(annotation: ast.expr) -> set[str]:
        if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
            annotation = ast.parse(annotation.value, mode="eval").body
        names: set[str] = set()
        for sub in ast.walk(annotation):
            if isinstance(sub, ast.Name):
                names.add(sub.id)
            elif isinstance(sub, ast.Attribute):
                names.add(sub.attr)
            elif isinstance(sub, ast.Constant) and sub.value is None:
                names.add("None")
        return names
