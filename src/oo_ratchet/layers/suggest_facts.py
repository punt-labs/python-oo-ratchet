"""What a ring suggestion reads from each module: IO, entry signals, Protocols."""

from __future__ import annotations

import ast
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from oo_ratchet.design.layer_config import LayerConfig, LayerConfigError
from oo_ratchet.design.layer_imports import LayerImports
from oo_ratchet.design.modules import Module, ModuleIndex
from oo_ratchet.design.targets import ImportTargets

from .io_sites import IoSites
from .strict import StrictViolations

ENTRY_LIBRARIES = ("argparse", "typer")


@dataclass(frozen=True, slots=True)
class ModuleFacts:
    """The evidence for one module: sorted, so every report is reproducible.

    ``forced`` is why the module cannot be placed at all, when it cannot.
    """

    name: str
    io: tuple[str, ...]
    entry: tuple[str, ...]
    protocols: tuple[str, ...]
    imports: tuple[str, ...]
    forced: str | None = None


class ConsoleScripts:
    """The modules the nearest pyproject's ``[project.scripts]`` names."""

    _targets: dict[str, str]
    _found: bool

    def __new__(cls, pyproject: Path | None) -> Self:
        self = super().__new__(cls)
        self._found = pyproject is not None
        self._targets = cls._read(pyproject)
        return self

    @property
    def found(self) -> bool:
        """Return whether a pyproject was there to read."""
        return self._found

    def script(self, module: str) -> str | None:
        """Return a script name whose target is in ``module``, if one is."""
        return self._targets.get(module)

    @classmethod
    def _read(cls, pyproject: Path | None) -> dict[str, str]:
        if pyproject is None:
            return {}
        try:
            table = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise LayerConfigError(f"cannot read {pyproject}: {exc}") from exc
        project = table.get("project", {})
        scripts = project.get("scripts", {}) if isinstance(project, dict) else None
        if not isinstance(scripts, dict):
            raise LayerConfigError(f"{pyproject}: [project.scripts] must be a table")
        found: dict[str, str] = {}
        for name, target in sorted(scripts.items(), reverse=True):
            if not isinstance(target, str):
                msg = f"{pyproject}: [project.scripts] {name} must be a string"
                raise LayerConfigError(msg)
            found[target.split(":")[0].strip()] = name
        return found


class PackageFacts:
    """Collect ``ModuleFacts`` for every non-root module of a package.

    Imports come from the gate's own edge extractor (``StrictViolations``), so
    re-export hops and literal dynamic imports count here exactly as they do
    when the gate checks the table.
    """

    _index: ModuleIndex
    _edges: StrictViolations
    _names: LayerImports
    _scripts: ConsoleScripts

    def __new__(cls, index: ModuleIndex, scripts: ConsoleScripts) -> Self:
        self = super().__new__(cls)
        self._index = index
        self._edges = StrictViolations(index, LayerConfig({}))
        self._names = LayerImports(index)
        self._scripts = scripts
        return self

    def all(self) -> list[ModuleFacts]:
        """Return the facts of each module below the package root, by name."""
        package = self._index.package_name
        bad = {row.rsplit(":", 1)[0] for row in self._edges.unresolvable()}
        rows = [
            self._of(m, bad)
            for m in self._index.modules()
            if self._names.canonical_name(m) != package
        ]
        return sorted(rows, key=lambda f: f.name)

    def _of(self, module: Module, bad: set[str]) -> ModuleFacts:
        name = self._names.name(module)
        canonical = self._names.canonical_name(module)
        io = IoSites(module, self._index.package_name).names()
        imports = {t for _, _, t in self._edges.targets(module)} - {canonical}
        return ModuleFacts(
            name,
            tuple(sorted(io)),
            self._entry(canonical, module),
            self._protocols(module),
            tuple(sorted(imports)),
            self._forced(name, canonical, unresolvable=str(module.path) in bad),
        )

    @staticmethod
    def _forced(name: str, canonical: str, *, unresolvable: bool) -> str | None:
        if name != canonical:
            return f"shadowed: another file is also module {canonical}"
        if unresolvable:
            return "unresolvable relative import climbs above the package root"
        return None

    def _entry(self, name: str, module: Module) -> tuple[str, ...]:
        roots = self._roots(module.tree)
        script = self._scripts.script(name)
        return (
            *(f"imports {lib}" for lib in ENTRY_LIBRARIES if lib in roots),
            *((f"console script {script}",) if script else ()),
        )

    @staticmethod
    def _roots(tree: ast.Module) -> set[str]:
        skip = ImportTargets.type_only(tree)
        roots: set[str] = set()
        for node in ast.walk(tree):
            if id(node) in skip:
                continue
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
                for node in module.tree.body
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
