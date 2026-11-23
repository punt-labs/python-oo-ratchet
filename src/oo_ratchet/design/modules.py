"""Parsed modules of one package tree, indexed for the design rules."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Self

from oo_ratchet.coupling.layout import PackageLayout

from .shape import ClassShape

if TYPE_CHECKING:
    from oo_ratchet.source_set import Source


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

    @property
    def import_key(self) -> str:
        """Return the logical import spelling, even for a shadowed file."""
        if not self.key.startswith("/"):
            return self.key
        parts = Path(self.key[1:]).with_suffix("").parts
        return PackageLayout._parts_to_key(parts)


class ModuleIndex:
    """Parse every module under a package root and index it by layout key.

    Files that do not parse are kept aside as skipped paths, never raised: the
    design check is advisory and reports on what it can read.
    """

    _layout: PackageLayout
    _modules: dict[str, Module]
    _skipped: list[Path]
    _package_name: str

    def __new__(cls, root: Source, *, package_name: str | None = None) -> Self:
        self = super().__new__(cls)
        self._layout = PackageLayout(root)
        self._package_name = package_name or self._layout.package_name
        self._modules = {}
        self._skipped = []
        paths = self._layout.root_files()
        for path in sorted(paths, key=lambda p: (p.name != "__init__.py", p)):
            self._add(path)
        return self

    @property
    def layout(self) -> PackageLayout:
        """Return the package layout the keys come from."""
        return self._layout

    @property
    def package_name(self) -> str:
        """Return the logical scan name, independent of symlink transport."""
        return self._package_name

    @property
    def skipped(self) -> list[Path]:
        """Return files that could not be read or parsed."""
        return list(self._skipped)

    def modules(self) -> list[Module]:
        """Return every parsed module in path order."""
        return sorted(self._modules.values(), key=lambda m: m.path)

    def key_for(self, path: Path) -> str:
        """Return a parsed file's unique identity, retaining shadowed paths."""
        key = self._layout.key_for(path)
        module = self._modules.get(key)
        return (
            key if module is not None and module.path == path else self._path_key(path)
        )

    def get(self, key: str) -> Module | None:
        """Return the module with layout key ``key``, if it was parsed."""
        return self._modules.get(key)

    def component(self, key: str) -> str:
        """Return the top-level sub-package a key belongs to ('' for the root)."""
        if key.startswith("/"):
            parts = Path(key[1:]).parts
            return parts[0] if len(parts) > 1 else ""
        head = key.split(".")[0]
        return head if self._layout.contains(head) else ""

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
        if key in self._modules:
            key = self._path_key(path)
        self._modules[key] = Module(key, path, tree, classes)

    def _path_key(self, path: Path) -> str:
        return "/" + self._layout.relative_path(path).as_posix()
