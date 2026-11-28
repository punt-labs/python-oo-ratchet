"""File openers in a module: bare ``open`` calls and the openers of ``io``."""

from __future__ import annotations

import ast
from typing import ClassVar, Self

from .builtin_open import BuiltinOpen


class IoUsage:
    """``io`` holds in-memory buffers (``StringIO``, ``BytesIO``) and file openers.

    An import of ``io`` is file IO only when the module uses a file opener from
    it: ``io.open``, ``io.FileIO`` or ``io.open_code``, called through the
    module or an alias of it, or imported by name with ``from io import``.
    ``io.StringIO``, ``io.BytesIO`` and wrappers over them touch no file.
    """

    MODULE: ClassVar[str] = "io"
    OPENERS: ClassVar[frozenset[str]] = frozenset({"open", "FileIO", "open_code"})
    _tree: ast.Module

    def __new__(cls, tree: ast.Module) -> Self:
        self = super().__new__(cls)
        self._tree = tree
        return self

    def bare_opens(self) -> list[ast.Call]:
        """Return the unbound bare ``open`` calls of the module."""
        return BuiltinOpen(self._tree).calls()

    def counts(self, node: ast.Import | ast.ImportFrom, name: str) -> bool:
        """Return whether the IO import ``name`` made by ``node`` is file IO."""
        return name != self.MODULE or self.opens_files(node)

    def opens_files(self, node: ast.Import | ast.ImportFrom) -> bool:
        """Return whether the ``io`` import ``node`` is used to open files."""
        if isinstance(node, ast.ImportFrom):
            return any(alias.name in self.OPENERS for alias in node.names)
        bound = {a.asname or a.name for a in node.names if a.name == self.MODULE}
        return any(self._opener_of(n, bound) for n in ast.walk(self._tree))

    def _opener_of(self, node: ast.AST, bound: set[str]) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr in self.OPENERS
            and isinstance(node.value, ast.Name)
            and node.value.id in bound
        )
