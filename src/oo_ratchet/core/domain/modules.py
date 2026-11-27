"""Parsed modules of one package tree, indexed for the design rules."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from .findings import Finding
from .shape import ClassShape

if TYPE_CHECKING:
    from pathlib import Path

    from .modulesource import ModuleSource


@dataclass(frozen=True, slots=True)
class Module:
    """One parsed source file and the classes it defines at top level."""

    key: str
    path: Path
    tree: ast.Module
    classes: dict[str, ClassShape]
    import_key: str
    """The logical import spelling, even for a shadowed file."""

    @property
    def is_package(self) -> bool:
        """Return whether the file is a package ``__init__``."""
        return self.path.name == "__init__.py"

    def finding(self, rule: str, line: int, symbol: str, detail: str) -> Finding:
        """Return a ``rule`` finding at ``line`` of this file."""
        return Finding(rule, str(self.path), line, symbol, detail)

    def import_froms(self) -> list[ast.ImportFrom]:
        """Return every ``from ... import`` statement, wherever it sits."""
        return [n for n in ast.walk(self.tree) if isinstance(n, ast.ImportFrom)]

    def package_parts(self) -> list[str]:
        """Return the dotted parts of the package this file sits in, from its key."""
        if self.import_key == "__init__":
            return []
        parts = self.import_key.split(".")
        return parts if self.is_package else parts[:-1]

    def reexport(self, name: str) -> tuple[ast.ImportFrom, str] | None:
        """Return the top-level import that binds ``name``, with its source name.

        The source name differs from ``name`` for ``from .core import Engine as
        PublicEngine``.
        """
        for node in self.tree.body:
            if not isinstance(node, ast.ImportFrom):
                continue
            for alias in node.names:
                if (alias.asname or alias.name) == name:
                    return node, alias.name
        return None


class ModuleIndex:
    """Parse every module under a package root and index it by layout key.

    Files that do not parse are kept aside as skipped paths, never raised: the
    design check is advisory and reports on what it can read.
    """

    _source: ModuleSource
    _modules: dict[str, Module]
    _skipped: list[Path]
    _package_name: str

    def __new__(cls, source: ModuleSource, *, package_name: str | None = None) -> Self:
        self = super().__new__(cls)
        self._source = source
        self._package_name = package_name or source.package_name
        self._modules = {}
        self._skipped = []
        paths = source.files()
        for path in sorted(paths, key=lambda p: (p.name != "__init__.py", p)):
            self._add(path)
        return self

    @property
    def source(self) -> ModuleSource:
        """Return the source files the keys come from."""
        return self._source

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
        key = self._source.key_for(path)
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
            parts = key[1:].split("/")
            return parts[0] if len(parts) > 1 else ""
        head = key.split(".")[0]
        return head if self._source.contains(head) else ""

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
        import_key = self._source.key_for(path)
        key = self._path_key(path) if import_key in self._modules else import_key
        self._modules[key] = Module(key, path, tree, classes, import_key)

    def _path_key(self, path: Path) -> str:
        return "/" + self._source.relative_path(path).as_posix()
