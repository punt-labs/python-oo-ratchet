"""Import-based IO dependencies, unbound bare open calls and Path file IO."""

from __future__ import annotations

import ast
from typing import ClassVar, Self

from .builtin_open import BuiltinOpen
from .findings import Finding, Rules
from .modules import Module
from .path_calls import PathCalls
from .targets import ImportTargets


class DomainIO:
    """Keep domain modules independent of IO libraries, irrespective of usage."""

    IO: ClassVar[tuple[str, ...]] = (
        "subprocess",
        "socket",
        "shutil",
        "json",
        "sqlite3",
        "httpx",
        "requests",
        "urllib.request",
        "typer",
        "rich",
        "mcp",
        "fastmcp",
        "logging.handlers",
        "os",
        "os.path",
        "pathlib",
        "io",
        "tempfile",
        "glob",
    )
    PATHLIB: ClassVar[str] = "pathlib"
    _module: Module

    def __new__(cls, module: Module) -> Self:
        self = super().__new__(cls)
        self._module = module
        return self

    def findings(self) -> list[Finding]:
        """Return one finding per IO import, bare unbound open and Path IO call."""
        out = [self._finding(node, name) for node, name in self._imports()]
        out.extend(
            self._finding(node, "open") for node in self._opens(self._module.tree)
        )
        out.extend(
            self._finding(node, self.PATHLIB)
            for node in self._path_calls(self._module.tree)
        )
        return out

    def targets(self) -> list[str]:
        """Return the sorted distinct IO targets.

        A bare ``open`` is ``builtins.open``; a file-system method on a ``Path``
        object is ``pathlib``, the module an import of it would be keyed by.
        """
        names = {name for _, name in self._imports()}
        if self._opens(self._module.tree):
            names.add("builtins.open")
        if self._path_calls(self._module.tree):
            names.add(self.PATHLIB)
        return sorted(names)

    @staticmethod
    def _path_calls(tree: ast.Module) -> list[ast.Call]:
        """Return the file-system calls on ``Path`` objects outside TYPE_CHECKING."""
        type_only = ImportTargets.type_only(tree)
        return [call for call in PathCalls(tree).calls() if id(call) not in type_only]

    @staticmethod
    def _opens(tree: ast.Module) -> list[ast.Call]:
        """Return the bare unbound ``open`` calls outside TYPE_CHECKING."""
        type_only = ImportTargets.type_only(tree)
        return [call for call in BuiltinOpen(tree).calls() if id(call) not in type_only]

    def _imports(self) -> list[tuple[ast.stmt, str]]:
        type_only = ImportTargets.type_only(self._module.tree)
        return [
            (node, name)
            for node in ast.walk(self._module.tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            and id(node) not in type_only
            for name in self._io_names(node)
        ]

    @classmethod
    def _io_names(cls, node: ast.Import | ast.ImportFrom) -> list[str]:
        return [name for name in dict.fromkeys(cls._imported(node)) if cls._is_io(name)]

    @classmethod
    def _imported(cls, node: ast.Import | ast.ImportFrom) -> list[str]:
        if isinstance(node, ast.Import):
            return [alias.name for alias in node.names]
        return cls._from_names(node)

    @classmethod
    def _from_names(cls, node: ast.ImportFrom) -> list[str]:
        if node.level:
            return []
        base = node.module or ""
        if cls._is_io(base):
            return [base]
        return [f"{base}.{alias.name}" for alias in node.names]

    @classmethod
    def is_io(cls, name: str) -> bool:
        """Return whether the dotted module ``name`` is, or is inside, an IO module."""
        return cls._is_io(name)

    @classmethod
    def _is_io(cls, name: str) -> bool:
        return any(name == io or name.startswith(io + ".") for io in cls.IO)

    def _finding(self, node: ast.stmt | ast.expr, symbol: str) -> Finding:
        return self._module.finding(
            Rules.DOMAIN_IO,
            node.lineno,
            symbol,
            "domain module depends on IO; use an injected port",
        )
