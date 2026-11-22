"""What one class definition holds: state, methods, accessors, abstractness."""

from __future__ import annotations

import ast
from typing import ClassVar, Self

from .state import StateProbe

type Method = ast.FunctionDef | ast.AsyncFunctionDef


class ClassShape:
    """Classify a ``ClassDef`` for the design rules.

    A class is *exempt* when it is a value or type declaration (exception,
    enum, dataclass, ``NamedTuple``, ``TypedDict``, pydantic model, or a
    value object defining ``__eq__``/``__hash__``), *abstract*
    when it is a ``Protocol``/``ABC`` or declares an ``@abstractmethod``, and a
    *subclass* when it names any base besides ``object``/``Generic``.
    """

    _VALUE_BASES: ClassVar[frozenset[str]] = frozenset(
        {
            "Enum", "IntEnum", "StrEnum", "Flag", "IntFlag", "ReprEnum",
            "Exception", "BaseException", "NamedTuple", "TypedDict", "BaseModel",
        }
    )  # fmt: skip
    _VALUE_DECORATORS: ClassVar[frozenset[str]] = frozenset(
        {"dataclass", "define", "frozen", "attrs", "dataclass_transform"}
    )
    _ABSTRACT_BASES: ClassVar[frozenset[str]] = frozenset({"Protocol", "ABC"})
    _NEUTRAL_BASES: ClassVar[frozenset[str]] = frozenset({"object", "Generic"})
    _ERROR_SUFFIXES: ClassVar[tuple[str, ...]] = ("Error", "Exception", "Warning")

    _node: ast.ClassDef
    _bases: tuple[str, ...]
    _methods: tuple[Method, ...]

    def __new__(cls, node: ast.ClassDef) -> Self:
        self = super().__new__(cls)
        self._node = node
        self._bases = tuple(
            name for name in map(cls._name, node.bases) if name is not None
        )
        self._methods = tuple(
            item
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        return self

    @property
    def name(self) -> str:
        """Return the class name."""
        return self._node.name

    @property
    def line(self) -> int:
        """Return the line the class is defined on."""
        return self._node.lineno

    @property
    def is_exempt(self) -> bool:
        """Return whether the class is a value/type shape the rules skip."""
        decorators = {self._name(d) for d in self._node.decorator_list}
        return bool(
            decorators & self._VALUE_DECORATORS
            or any(b in self._VALUE_BASES for b in self._bases)
            or any(b.endswith(self._ERROR_SUFFIXES) for b in self._bases)
            or any(m.name in {"__eq__", "__hash__"} for m in self._methods)
        )

    @property
    def is_abstract(self) -> bool:
        """Return whether the class declares an interface."""
        return any(b in self._ABSTRACT_BASES for b in self._bases) or any(
            self._name(d) == "abstractmethod"
            for m in self._methods
            for d in m.decorator_list
        )

    @property
    def is_subclass(self) -> bool:
        """Return whether the class inherits from anything but ``object``."""
        return any(b not in self._NEUTRAL_BASES for b in self._bases)

    @property
    def has_state(self) -> bool:
        """Return whether any instance of the class carries its own data."""
        return StateProbe(self._node, self._methods).found

    def method_names(self) -> list[str]:
        """Return the names of every method the class body defines."""
        return [m.name for m in self._methods]

    def public_methods(self) -> list[str]:
        """Return public method names (``__call__`` counts; properties do not)."""
        return [
            m.name
            for m in self._methods
            if (not m.name.startswith("_") or m.name == "__call__")
            and not self._is_property(m)
        ]

    def accessors(self) -> list[str]:
        """Return public properties and ``get_*`` methods that only read a field."""
        return [
            m.name
            for m in self._methods
            if not m.name.startswith("_")
            and (self._is_property(m) or m.name.startswith("get_"))
            and self._only_returns_field(m)
        ]

    def public_members(self) -> int:
        """Return how many public methods and properties the class exposes."""
        return sum(
            1
            for m in self._methods
            if not m.name.startswith("_") and not self._is_setter(m)
        )

    @classmethod
    def _is_property(cls, method: Method) -> bool:
        return any(
            cls._name(d) in {"property", "cached_property"}
            for d in method.decorator_list
        )

    @staticmethod
    def _is_setter(method: Method) -> bool:
        return any(
            isinstance(d, ast.Attribute) and d.attr in {"setter", "deleter"}
            for d in method.decorator_list
        )

    @staticmethod
    def _only_returns_field(method: Method) -> bool:
        body = [
            s
            for s in method.body
            if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
        ]
        if len(body) != 1 or not isinstance(body[0], ast.Return):
            return False
        value = body[0].value
        return (
            isinstance(value, ast.Attribute)
            and isinstance(value.value, ast.Name)
            and value.value.id == "self"
        )

    @staticmethod
    def _name(node: ast.expr) -> str | None:
        if isinstance(node, ast.Call):
            node = node.func
        if isinstance(node, ast.Subscript):
            node = node.value
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None
