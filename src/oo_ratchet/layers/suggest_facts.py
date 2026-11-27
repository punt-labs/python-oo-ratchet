"""What a ring suggestion reads from each module: IO, entry signals, Protocols."""

from __future__ import annotations

import ast
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Self

from oo_ratchet.design.layer_config import LayerConfig, LayerConfigError
from oo_ratchet.design.layer_imports import LayerImports
from oo_ratchet.design.modules import Module, ModuleIndex
from oo_ratchet.design.protocol_imports import ProtocolImports
from oo_ratchet.design.targets import ImportTargets

from .io_sites import IoSites
from .strict import StrictViolations

ENTRY_LIBRARIES = ("argparse", "typer")
ROOT_EVIDENCE = "package root (placed in entry by vox, lux and z-spec)"


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
    root: bool = False


class ConsoleScripts:
    """The modules the nearest pyproject's ``[project.scripts]`` names."""

    _targets: dict[str, list[str]]
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

    def scripts(self, module: str) -> list[str]:
        """Return the sorted names of the scripts whose target is ``module``."""
        return sorted(self._targets.get(module, []))

    @classmethod
    def _read(cls, pyproject: Path | None) -> dict[str, list[str]]:
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
        found: dict[str, list[str]] = {}
        for name, target in scripts.items():
            if not isinstance(target, str):
                msg = f"{pyproject}: [project.scripts] {name} must be a string"
                raise LayerConfigError(msg)
            found.setdefault(target.split(":")[0].strip(), []).append(name)
        return found


class PackageFacts:
    """Collect ``ModuleFacts`` for every module of a package, the root included.

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
        """Return the facts of each module, the package root included, by name.

        The gate names a module by its canonical name, so files that share one
        (``pkg/a.py`` and ``pkg/a/__init__.py``) are one unclassifiable entry
        under that name, listing every file; none of them is placed.
        """
        package = self._index.package_name
        bad = {row.rsplit(":", 1)[0] for row in self._edges.unresolvable()}
        groups: dict[str, list[Module]] = {}
        for module in self._index.modules():
            name = self._names.canonical_name(module)
            groups.setdefault(name, []).append(module)
        rows = [
            self._of(name, mods[0], bad)
            if len(mods) == 1
            else self._shadowed(name, mods)
            for name, mods in groups.items()
        ]
        rows = [self._as_root(f) if f.name == package else f for f in rows]
        return sorted(rows, key=lambda f: f.name)

    @staticmethod
    def _as_root(facts: ModuleFacts) -> ModuleFacts:
        """Mark the package root; adopters place it in ``entry``."""
        return replace(facts, entry=(ROOT_EVIDENCE,), root=True)

    def _shadowed(self, name: str, mods: list[Module]) -> ModuleFacts:
        files = ", ".join(
            sorted(self._index.layout.relative_path(m.path).as_posix() for m in mods)
        )
        why = f"shadowed: {len(mods)} files are module {name}: {files}"
        return ModuleFacts(name, (), (), (), (), why)

    def _of(self, name: str, module: Module, bad: set[str]) -> ModuleFacts:
        io = IoSites(module, self._index.package_name).names()
        imports = {t for _, _, t in self._edges.targets(module)} - {name}
        unresolvable = (
            "unresolvable relative import climbs above the package root"
            if str(module.path) in bad
            else None
        )
        return ModuleFacts(
            name,
            tuple(sorted(io)),
            self._entry(name, module),
            self._protocols(module),
            tuple(sorted(imports)),
            unresolvable,
        )

    def _entry(self, name: str, module: Module) -> tuple[str, ...]:
        roots = self._roots(module.tree)
        return (
            *(f"imports {lib}" for lib in ENTRY_LIBRARIES if lib in roots),
            *(f"console script {s}" for s in self._scripts.scripts(name)),
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
        """Return top-level classes whose base resolves to typing's Protocol."""
        markers = ProtocolImports(module).names()
        return tuple(
            sorted(
                node.name
                for node in module.tree.body
                if isinstance(node, ast.ClassDef)
                and any(PackageFacts._base(b) in markers for b in node.bases)
            )
        )

    @staticmethod
    def _base(base: ast.expr) -> str:
        return ast.unparse(base.value if isinstance(base, ast.Subscript) else base)
