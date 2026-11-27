"""What a ring suggestion reads from each module: IO, entry signals, Protocols."""

from __future__ import annotations

import ast
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from oo_ratchet.design.layer_config import LayerConfigError
from oo_ratchet.design.layer_imports import LayerImports
from oo_ratchet.design.modules import Module, ModuleIndex

from .io_sites import IoSites

ENTRY_LIBRARIES = ("argparse", "typer")


@dataclass(frozen=True, slots=True)
class ModuleFacts:
    """The evidence for one module: sorted, so every report is reproducible."""

    name: str
    io: tuple[str, ...]
    entry: tuple[str, ...]
    protocols: tuple[str, ...]
    imports: tuple[str, ...]


class ConsoleScripts:
    """The modules the nearest pyproject's ``[project.scripts]`` names."""

    _targets: dict[str, str]

    def __new__(cls, pyproject: Path | None) -> Self:
        self = super().__new__(cls)
        self._targets = cls._read(pyproject)
        return self

    def script(self, module: str) -> str | None:
        """Return a script name whose target is in ``module``, if one is."""
        return self._targets.get(module)

    @staticmethod
    def _read(pyproject: Path | None) -> dict[str, str]:
        if pyproject is None:
            return {}
        try:
            table = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise LayerConfigError(f"cannot read {pyproject}: {exc}") from exc
        scripts = table.get("project", {}).get("scripts", {})
        found: dict[str, str] = {}
        for name, target in sorted(scripts.items(), reverse=True):
            if isinstance(target, str):
                found[target.split(":")[0].strip()] = name
        return found


class PackageFacts:
    """Collect ``ModuleFacts`` for every non-root module of a package."""

    _index: ModuleIndex
    _imports: LayerImports
    _scripts: ConsoleScripts

    def __new__(cls, index: ModuleIndex, scripts: ConsoleScripts) -> Self:
        self = super().__new__(cls)
        self._index = index
        self._imports = LayerImports(index)
        self._scripts = scripts
        return self

    def all(self) -> list[ModuleFacts]:
        """Return the facts of each module below the package root, by name."""
        package = self._index.package_name
        names = {self._imports.canonical_name(m): m for m in self._index.modules()}
        return [self._of(n, names[n]) for n in sorted(names) if n != package]

    def _of(self, name: str, module: Module) -> ModuleFacts:
        io = IoSites(module, self._index.package_name).names()
        imports = {t for _, _, t in self._imports.imports(module)} - {name}
        return ModuleFacts(
            name,
            tuple(sorted(io)),
            self._entry(name, module),
            self._protocols(module),
            tuple(sorted(imports)),
        )

    def _entry(self, name: str, module: Module) -> tuple[str, ...]:
        roots = self._roots(module.tree)
        script = self._scripts.script(name)
        return (
            *(f"imports {lib}" for lib in ENTRY_LIBRARIES if lib in roots),
            *((f"console script {script}",) if script else ()),
        )

    @staticmethod
    def _roots(tree: ast.Module) -> set[str]:
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                roots.add(node.module.split(".")[0])
        return roots

    @staticmethod
    def _protocols(module: Module) -> tuple[str, ...]:
        return tuple(
            sorted(
                node.name
                for node in ast.walk(module.tree)
                if isinstance(node, ast.ClassDef)
                and any(PackageFacts._is_protocol(base) for base in node.bases)
            )
        )

    @staticmethod
    def _is_protocol(base: ast.expr) -> bool:
        if isinstance(base, ast.Subscript):
            base = base.value
        if isinstance(base, ast.Attribute):
            return base.attr == "Protocol"
        return isinstance(base, ast.Name) and base.id == "Protocol"
