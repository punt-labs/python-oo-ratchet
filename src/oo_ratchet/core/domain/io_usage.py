"""File openers in a module: bare ``open`` calls and the openers of ``io``."""

from __future__ import annotations

import ast
from typing import ClassVar, Self, TypeGuard

from .builtin_open import BuiltinOpen


class IoUsage:
    """``io`` holds in-memory buffers (``StringIO``, ``BytesIO``) and file openers.

    An import of ``io`` is file IO unless every use of it is an attribute access
    to a known in-memory member (``io.StringIO``, ``io.BytesIO``,
    ``io.TextIOWrapper`` ...). ``io.open``, ``io.FileIO``, ``io.open_code``, an
    unknown attribute, ``getattr(io, ...)``, passing ``io`` on or aliasing it
    all count, and so does ``from io import`` of an opener or ``*``. An unused
    ``import io`` does not.
    """

    MODULE: ClassVar[str] = "io"
    OPENERS: ClassVar[frozenset[str]] = frozenset({"open", "FileIO", "open_code"})
    MEMORY: ClassVar[frozenset[str]] = frozenset(
        {
            "StringIO",
            "BytesIO",
            "TextIOWrapper",
            "BufferedReader",
            "BufferedWriter",
            "BufferedRandom",
            "BufferedRWPair",
            "IOBase",
            "RawIOBase",
            "BufferedIOBase",
            "TextIOBase",
            "IncrementalNewlineDecoder",
            "UnsupportedOperation",
            "BlockingIOError",
            "DEFAULT_BUFFER_SIZE",
            "SEEK_SET",
            "SEEK_CUR",
            "SEEK_END",
            "text_encoding",
        }
    )
    _tree: ast.Module
    _leaked: frozenset[str]

    def __new__(cls, tree: ast.Module) -> Self:
        self = super().__new__(cls)
        self._tree = tree
        self._leaked = cls._leaks(tree)
        return self

    @staticmethod
    def bare_opens(tree: ast.Module) -> list[ast.Call]:
        """Return the unbound bare ``open`` calls of ``tree``."""
        return BuiltinOpen(tree).calls()

    def counts(self, node: ast.Import | ast.ImportFrom, name: str) -> bool:
        """Return whether the IO import ``name`` made by ``node`` is file IO."""
        return name != self.MODULE or self.opens_files(node)

    def opens_files(self, node: ast.Import | ast.ImportFrom) -> bool:
        """Return whether the ``io`` import ``node`` is used to open files."""
        if isinstance(node, ast.ImportFrom):
            return any(a.name == "*" or a.name in self.OPENERS for a in node.names)
        return any(
            (a.asname or a.name) in self._leaked
            for a in node.names
            if a.name == self.MODULE
        )

    @classmethod
    def _leaks(cls, tree: ast.Module) -> frozenset[str]:
        """Return the names read other than as ``<name>.<in-memory member>``."""
        safe = cls._members(tree)
        return frozenset(
            n.id for n in ast.walk(tree) if cls._is_read(n) and id(n) not in safe
        )

    @classmethod
    def _members(cls, tree: ast.Module) -> set[int]:
        """Return the ids of names that are the object of an in-memory member."""
        return {
            id(n.value)
            for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and cls._is_member(n)
        }

    @classmethod
    def _is_member(cls, node: ast.Attribute) -> bool:
        return node.attr in cls.MEMORY and isinstance(node.value, ast.Name)

    @staticmethod
    def _is_read(node: ast.AST) -> TypeGuard[ast.Name]:
        return isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
