"""The text of a sub-package's ``__init__.py``, read by an adapter."""

from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PackageInit:
    """A sub-package's name and the text of its ``__init__.py``.

    ``text`` is ``None`` when the file is absent or unreadable.
    """

    name: str
    text: str | None

    def interface_width(self) -> int:
        """Return ``len(__all__)``, else the count of public re-exported names."""
        if self.text is None:
            return 0
        try:
            tree = ast.parse(self.text)
        except SyntaxError:
            # Package interface width is a display-only metric; an unparseable
            # __init__.py contributes 0 here. The gate is unaffected: the scorer
            # records the same file as an error and the ratchet fails on it when
            # touched.
            return 0
        explicit = self._all_width(tree)
        return explicit if explicit is not None else self._import_width(tree)

    @staticmethod
    def _all_width(tree: ast.Module) -> int | None:
        """Return ``len(__all__)`` for the package init, else ``None``."""
        for node in ast.iter_child_nodes(tree):
            elements = PackageInit._all_elements(node)
            if elements is not None:
                return len(elements)
        return None

    @staticmethod
    def _all_elements(node: ast.AST) -> list[ast.expr] | None:
        """Return the entries of an ``__all__ = [...]`` assignment, else ``None``."""
        if not isinstance(node, ast.Assign):
            return None
        if not isinstance(node.value, (ast.List, ast.Tuple)):
            return None
        named = any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
        return node.value.elts if named else None

    @staticmethod
    def _import_width(tree: ast.Module) -> int:
        return sum(
            1
            for node in ast.iter_child_nodes(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
            for alias in node.names
            if not alias.name.startswith("_")
        )
