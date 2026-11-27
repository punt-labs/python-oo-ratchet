"""What a ring suggestion reads from each module: IO, entry signals, ring markers."""

from __future__ import annotations

import ast
import re
import tomllib
from dataclasses import replace
from pathlib import Path
from typing import Self

from oo_ratchet.core.domain.layer_config import LayerConfig, LayerConfigError
from oo_ratchet.core.domain.layer_imports import LayerImports
from oo_ratchet.core.domain.modules import Module, ModuleIndex
from oo_ratchet.core.domain.targets import ImportTargets

from .io_sites import IoSites
from .package_edges import PackageEdges
from .suggest_model import ModuleFacts

ENTRY_LIBRARIES = ("argparse", "typer")
_NAME = r"[^\W\d]\w*"
_DOTTED = rf"{_NAME}(?:\.{_NAME})*"
_EXTRA = r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"
_EXTRAS = rf"\[\s*(?:{_EXTRA}(?:\s*,\s*{_EXTRA})*)?\s*\]"
# module[.module]*, then optionally ":" object[.object]*, then optionally
# [extra, ...] of PEP 508 extra names; the list may be empty, as PEP 508 allows.
# Anchored by fullmatch: importlib.metadata's own pattern accepts any text
# inside the brackets.
ENTRY_POINT = re.compile(
    rf"(?P<module>{_DOTTED})(?:\s*:\s*{_DOTTED})?(?:\s*{_EXTRAS})?"
)
ROOT_EVIDENCE = "package root (placed in entry by vox, lux and z-spec)"


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

    @staticmethod
    def _module(target: object) -> str | None:
        """Return the module of a ``module[:object] [extras]`` value, or ``None``."""
        match = (
            ENTRY_POINT.fullmatch(target.strip()) if isinstance(target, str) else None
        )
        return match.group("module") if match else None

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
            module = cls._module(target)
            if module is None:
                msg = f"{pyproject}: [project.scripts] {name!r}: {target!r} is not"
                raise LayerConfigError(f"{msg} an entry point (module[:object])")
            found.setdefault(module, []).append(name)
        return found


class PackageFacts:
    """Collect ``ModuleFacts`` for every module of a package, the root included.

    Imports come from the gate's own edge extractor (``StrictViolations``), so
    re-export hops and literal dynamic imports count here exactly as they do
    when the gate checks the table.
    """

    _index: ModuleIndex
    _edges: PackageEdges
    _names: LayerImports
    _scripts: ConsoleScripts

    def __new__(cls, index: ModuleIndex, scripts: ConsoleScripts) -> Self:
        self = super().__new__(cls)
        self._index = index
        self._edges = PackageEdges(index, LayerConfig({}))
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
        return replace(facts, entry=(ROOT_EVIDENCE, *facts.entry), root=True)

    def _shadowed(self, name: str, mods: list[Module]) -> ModuleFacts:
        files = ", ".join(
            sorted(self._index.source.relative_path(m.path).as_posix() for m in mods)
        )
        why = f"shadowed: {len(mods)} files are module {name}: {files}"
        return ModuleFacts(name, (), (), (), why)

    def _of(self, name: str, module: Module, bad: set[str]) -> ModuleFacts:
        io = IoSites(module, self._index.package_name).names()
        imports = {t for _, _, t in self._edges.targets(module)} - {name}
        unresolvable = (
            "unresolvable relative import climbs above the package root"
            if str(module.path) in bad
            else None
        )
        marker, problem = self._marker(module)
        return ModuleFacts(
            name,
            tuple(sorted(io)),
            self._entry(name, module),
            tuple(sorted(imports)),
            unresolvable,
            marker=marker,
            marker_problem=problem,
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
    def _marker(module: Module) -> tuple[str | None, str | None]:
        """Return the top-level ``__ring__`` string as ``(marker, problem)``.

        The last assignment wins. A value that is not a string literal is a
        problem, not a ring; the module is never imported.
        """
        found: tuple[str | None, str | None] = (None, None)
        for node in module.tree.body:
            value = PackageFacts._assigned(node)
            if value is None:
                continue
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                found = (value.value, None)
            else:
                found = (None, "__ring__ must be a string literal")
        return found

    @staticmethod
    def _assigned(node: ast.stmt) -> ast.expr | None:
        """Return the value a top-level ``__ring__ = ...`` statement assigns."""
        value: ast.expr | None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        else:
            return None
        named = any(isinstance(t, ast.Name) and t.id == "__ring__" for t in targets)
        return value if named else None


class SuggestNames:
    """The ``[tool.oo-ratchet.suggest]`` table as written: names per ring.

    ``NameConvention`` checks the keys and values; this only finds the table.
    """

    _table: dict[str, object]

    def __new__(cls, pyproject: Path | None) -> Self:
        self = super().__new__(cls)
        self._table = cls._read(pyproject)
        return self

    @property
    def table(self) -> dict[str, object]:
        """Return the configured names per ring; empty when none are configured."""
        return self._table

    @classmethod
    def _read(cls, pyproject: Path | None) -> dict[str, object]:
        if pyproject is None:
            return {}
        try:
            text = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise LayerConfigError(f"cannot read {pyproject}: {exc}") from exc
        node: object = text
        for key in ("tool", "oo-ratchet", "suggest"):
            if not isinstance(node, dict) or key not in node:
                return {}
            node = node[key]
        if not isinstance(node, dict):
            raise LayerConfigError(
                f"{pyproject}: [tool.oo-ratchet.suggest] is not a table"
            )
        return node
