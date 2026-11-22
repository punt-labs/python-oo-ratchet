"""Resolve imports to full dotted names, including imported submodules."""

from __future__ import annotations

import ast
import os.path
from pathlib import Path
from typing import Self

from .modules import Module, ModuleIndex


class LayerImports:
    """Resolve relative and absolute imports against the scanned module set."""

    _package: str
    _names: frozenset[str]

    def __new__(cls, index: ModuleIndex) -> Self:
        self = super().__new__(cls)
        self._package = Path(os.path.normpath(index.layout.root.absolute())).name
        self._names = frozenset(
            self.canonical_name(module) for module in index.modules()
        )
        return self

    def name(self, module: Module) -> str:
        """Return a unique namespace, normalizing root __init__."""
        if module.key.startswith("/"):
            return self._package + ":" + module.key[1:]
        return self._package + ("" if module.key == "__init__" else f".{module.key}")

    def canonical_name(self, module: Module) -> str:
        """Return the config/import-facing name independent of shadowing."""
        key = module.import_key
        return self._package + ("" if key == "__init__" else f".{key}")

    def imports(self, module: Module) -> list[tuple[ast.stmt, str, str]]:
        """Return (node, imported symbol, target module), type-only included."""
        rows: list[tuple[ast.stmt, str, str]] = []
        for node in ast.walk(module.tree):
            if isinstance(node, ast.Import):
                rows.extend((node, alias.name, alias.name) for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = self._base(module, node, self.canonical_name(module))
                for alias in node.names:
                    child = f"{base}.{alias.name}"
                    target = child if child in self._names else base
                    rows.append((node, alias.name, target))
        return [row for row in rows if row[2] in self._names]

    @staticmethod
    def _base(module: Module, node: ast.ImportFrom, name: str) -> str:
        if not node.level:
            return node.module or ""
        parts = name.split(".")
        package = parts if module.is_package else parts[:-1]
        if node.level > len(package):
            return ""
        base = package[: len(package) - node.level + 1]
        return ".".join(base + ([node.module] if node.module else []))
