"""File IO done through methods of ``pathlib.Path`` objects."""

from __future__ import annotations

import ast
from typing import ClassVar, Self

from .path_types import PathTypes


class PathCalls:
    """The calls in a module that touch the file system through a ``Path``.

    A call counts when its receiver is evidenced to be a ``Path`` (see
    ``PathTypes``) and the method reads, writes, lists or inspects the file
    system, or when it is ``Path.cwd()`` or ``Path.home()``. A method of an
    object with no path evidence never counts, whatever it is called.
    """

    METHODS: ClassVar[frozenset[str]] = frozenset(
        {
            "read_text",
            "read_bytes",
            "write_text",
            "write_bytes",
            "open",
            "iterdir",
            "glob",
            "rglob",
            "walk",
            "exists",
            "is_file",
            "is_dir",
            "is_symlink",
            "is_junction",
            "is_mount",
            "is_socket",
            "is_fifo",
            "is_block_device",
            "is_char_device",
            "stat",
            "lstat",
            "owner",
            "group",
            "samefile",
            "mkdir",
            "rmdir",
            "unlink",
            "rename",
            "replace",
            "touch",
            "chmod",
            "lchmod",
            "symlink_to",
            "hardlink_to",
            "readlink",
            "resolve",
            "expanduser",
        }
    )
    CLASS_METHODS: ClassVar[frozenset[str]] = frozenset({"cwd", "home"})
    _tree: ast.Module
    _types: PathTypes

    def __new__(cls, tree: ast.Module) -> Self:
        self = super().__new__(cls)
        self._tree = tree
        self._types = PathTypes(tree)
        return self

    def calls(self) -> list[ast.Call]:
        """Return the file-system calls on path objects, in source order."""
        if not self._types.has_path_class():
            return []
        return [
            node
            for node in ast.walk(self._tree)
            if isinstance(node, ast.Call) and self._is_io(node)
        ]

    def _is_io(self, node: ast.Call) -> bool:
        func = node.func
        if not isinstance(func, ast.Attribute):
            return False
        if self._types.is_class(func.value):
            return func.attr in self.CLASS_METHODS
        return func.attr in self.METHODS and self._types.is_path(func.value)
