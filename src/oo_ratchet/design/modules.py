"""Parsed modules of one package tree, indexed for the design rules."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from oo_ratchet.coupling.layout import PackageLayout

from .shape import ClassShape


@dataclass(frozen=True, slots=True)
class Module:
    """One parsed source file and the classes it defines at top level."""

    key: str
    path: Path
    tree: ast.Module
    classes: dict[str, ClassShape]

    @property
    def is_package(self) -> bool:
        """Return whether the file is a package ``__init__``."""
        return self.path.name == "__init__.py"


class ModuleIndex:
    """Parse every module under a package root and index it by layout key.

    Files that do not parse are kept aside as skipped paths, never raised: the
    design check is advisory and reports on what it can read.
    """

    _layout: PackageLayout
    _modules: dict[str, Module]
    _skipped: list[Path]

    def __new__(cls, root: Path) -> Self:
        self = super().__new__(cls)
        self._layout = PackageLayout(root)
        self._modules = {}
        self._skipped = []
        for path in self._layout.root_files():
            self._add(path)
        return self

    @property
    def layout(self) -> PackageLayout:
        """Return the package layout the keys come from."""
        return self._layout

    @property
    def skipped(self) -> list[Path]:
        """Return files that could not be read or parsed."""
        return list(self._skipped)

    def modules(self) -> list[Module]:
        """Return every parsed module in path order."""
        return list(self._modules.values())

    def get(self, key: str) -> Module | None:
        """Return the module with layout key ``key``, if it was parsed."""
        return self._modules.get(key)

    def component(self, key: str) -> str:
        """Return the top-level sub-package a key belongs to ('' for the root)."""
        head = key.split(".")[0]
        return head if (self._layout.root / head).is_dir() else ""

    def interface_methods(self) -> tuple[frozenset[str], ...]:
        """Return the method names of each abstract class in the tree."""
        return tuple(
            frozenset(shape.method_names())
            for module in self._modules.values()
            for shape in module.classes.values()
            if shape.is_abstract
        )

    def _add(self, path: Path) -> None:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
            self._skipped.append(path)
            return
        classes = {
            node.name: ClassShape(node)
            for node in tree.body
            if isinstance(node, ast.ClassDef)
        }
        key = self._layout.key_for(path)
        self._modules[key] = Module(key, path, tree, classes)
