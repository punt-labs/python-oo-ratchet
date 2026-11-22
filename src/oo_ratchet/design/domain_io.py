"""Syntactic IO imports and filesystem/environment use in domain modules."""

from __future__ import annotations

import ast
from typing import ClassVar, Self

from .alias_scopes import AliasScopes
from .builtin_open import BuiltinOpen
from .findings import Finding, Rules
from .modules import Module


class DomainIO:
    """Resolve import aliases and simple Path assignments without executing code."""

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
    )
    FS: ClassVar[frozenset[str]] = frozenset(
        {
            "open",
            "read_text",
            "read_bytes",
            "write_text",
            "write_bytes",
            "touch",
            "mkdir",
            "rmdir",
            "unlink",
            "rename",
            "replace",
            "iterdir",
            "glob",
            "rglob",
            "exists",
            "is_file",
            "is_dir",
            "is_symlink",
            "isfile",
            "isdir",
            "islink",
            "lexists",
            "isjunction",
            "isdevdrive",
            "sameopenfile",
            "stat",
            "lstat",
            "resolve",
            "absolute",
            "cwd",
            "home",
            "chmod",
            "chown",
            "symlink_to",
            "hardlink_to",
            "getenv",
            "putenv",
            "unsetenv",
            "getcwd",
            "chdir",
            "listdir",
            "scandir",
            "remove",
            "removedirs",
            "makedirs",
            "walk",
            "access",
            "readlink",
            "expanduser",
            "expandvars",
            "getsize",
            "getmtime",
            "getatime",
            "getctime",
            "ismount",
            "samefile",
            "realpath",
            "abspath",
            "environ",
        }
    )
    _module: Module
    _aliases: AliasScopes

    def __new__(cls, module: Module) -> Self:
        self = super().__new__(cls)
        self._module = module
        self._aliases = AliasScopes(module.tree)
        return self

    def findings(self) -> list[Finding]:
        """Return IO import findings and unqualified builtin open calls."""
        imports = self._imports()
        uses = self._filesystem_uses()
        out = [
            self._finding(node, symbol)
            for node, symbol, name in imports
            if self._is_io(name) or self._uses_filesystem(name, uses)
        ]
        out.extend(self._open_calls())
        return out

    def _imports(self) -> list[tuple[ast.stmt, str, str]]:
        imports: list[tuple[ast.stmt, str, str]] = []
        for node in ast.walk(self._module.tree):
            if isinstance(node, ast.Import):
                imports.extend((node, alias.name, alias.name) for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                for alias in node.names:
                    name = f"{node.module}.{alias.name}"
                    imports.append((node, alias.name, name))
        return imports

    @staticmethod
    def _uses_filesystem(name: str, uses: set[str]) -> bool:
        return name.split(".")[0] in {"os", "pathlib"} and any(
            use == name or use.startswith(name + ".") for use in uses
        )

    def _open_calls(self) -> list[Finding]:
        out = [
            self._finding(node, "open")
            for node in BuiltinOpen(self._module.tree).calls()
        ]
        out.extend(
            self._finding(node, "open")
            for node in ast.walk(self._module.tree)
            if isinstance(node, ast.Call) and self._name(node.func) == "builtins.open"
        )
        return out

    def _filesystem_uses(self) -> set[str]:
        uses = {
            self._name(node.func)
            for node in ast.walk(self._module.tree)
            if isinstance(node, ast.Call)
        }
        uses.update(
            self._name(node)
            for node in ast.walk(self._module.tree)
            if isinstance(node, (ast.Name, ast.Attribute))
            and self._name(node).startswith("os.environ")
        )
        return {name for name in uses if name.rsplit(".", 1)[-1] in self.FS}

    def _name(self, node: ast.AST) -> str:
        return self._aliases.name(node)

    @classmethod
    def _is_io(cls, name: str) -> bool:
        return any(name == io or name.startswith(io + ".") for io in cls.IO)

    def _finding(self, node: ast.stmt | ast.expr, symbol: str) -> Finding:
        return Finding(
            Rules.DOMAIN_IO,
            str(self._module.path),
            node.lineno,
            symbol,
            "domain module depends on IO",
        )
