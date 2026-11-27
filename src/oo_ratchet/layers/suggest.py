"""``layers --suggest``: print a starter ring table for a human to review."""

from __future__ import annotations

from collections.abc import Callable
from typing import Self

from oo_ratchet.coupling.outcome import Outcome
from oo_ratchet.design.layer_table import LayerTable
from oo_ratchet.design.modules import ModuleIndex
from oo_ratchet.source_set import Source, SourceSet

from .ring_intent import NameConvention, RingIntent
from .scan import LayersScanError
from .suggest_facts import ConsoleScripts, PackageFacts, SuggestNames
from .suggest_model import ModuleFacts, Verdict
from .suggest_rules import RingRules
from .suggest_table import RingTable
from .suggest_text import SafeText

HEADER = (
    "# oo-ratchet layers --suggest {package}: a starting point, never applied.",
    "# Nothing was written. A wrong ring lets forbidden imports pass: review each",
    "# reason below, then copy the table into pyproject.toml yourself.",
    "# A ring comes from intent, never from a guess: a declaration (a module-level",
    '# __ring__ = "domain" string, or an existing fixed-form [tool.oo-ratchet.layers]',
    "# table), then a package name (domain, model, core suggest domain; adapters,",
    "# infra suggest adapters; [tool.oo-ratchet.suggest] replaces the names). The",
    "# one ring taken from evidence is entry: argparse, typer or a console script.",
    "# A module that reaches IO, directly or through imports, is never domain: that",
    "# is a CONFLICT, printed with the import path. A module with no intent stays",
    "# unclassified, with its evidence. The gate lets domain import only domain and",
    "# application import only application and domain, so a module importing a ring",
    "# it may not is a conflict too. A glob such as pkg.sub.* also claims any module",
    "# added later under that prefix. The package root goes in entry whatever it",
    "# imports, as vox, lux and z-spec place theirs; it is unclassified instead when",
    "# a non-entry module imports it or it has a relative import above the package.",
)
NO_PYPROJECT = "# No pyproject.toml was found: console scripts were not read."


class Suggestion:
    """Propose a ring for each module of a package from declared or named intent.

    Reads the package and the nearest pyproject's ``[project.scripts]``,
    ``[tool.oo-ratchet.suggest]`` and fixed-form layers table, if any. It
    returns text only and writes no file.
    """

    _src: Source
    _verdicts: dict[str, Verdict]
    _modules: tuple[str, ...]
    _package: str
    _scripts: bool

    def __new__(cls, src: Source) -> Self:
        self = super().__new__(cls)
        self._src = src
        index = cls._index(src)
        nearest = LayerTable.nearest(src)
        scripts = ConsoleScripts(nearest)
        facts = PackageFacts(index, scripts).all()
        cls._require_modules(facts, src)
        names = NameConvention(SuggestNames(nearest).table)
        intent = RingIntent(LayerTable.ordered(LayerTable.load(src)), names)
        self._verdicts = RingRules(facts, intent, index.package_name).verdicts()
        self._modules = tuple(sorted(self._verdicts))
        self._package = index.package_name
        self._scripts = scripts.found
        return self

    @staticmethod
    def _index(src: Source) -> ModuleIndex:
        SourceSet(src).require_package(LayersScanError)
        index = ModuleIndex(src)
        if index.skipped:
            names = ", ".join(sorted(str(p) for p in index.skipped))
            raise LayersScanError(f"cannot read or parse: {names}")
        return index

    @staticmethod
    def _require_modules(facts: list[ModuleFacts], src: Source) -> None:
        """Reject a package with no module below the root, as the gate does."""
        if not any("." in fact.name for fact in facts):
            raise LayersScanError(f"no modules to check under {src}")

    def outcome(self) -> Outcome:
        """Return the table and the reasons; the exit code is always 0."""
        rings = {n: v.ring for n, v in self._verdicts.items() if v.ring}
        table = RingTable(list(self._modules), rings).render()
        header = tuple(
            line.format(package=SafeText.comment(self._package)) for line in HEADER
        )
        missing = () if self._scripts else (NO_PYPROJECT,)
        return Outcome.passed(*header, *missing, *table, *self._notes())

    def _notes(self) -> list[str]:
        ringed = [n for n in self._modules if self._verdicts[n].ring]
        clash = [n for n in self._modules if self._verdicts[n].conflict]
        free = [n for n in self._modules if n not in ringed and n not in clash]
        lines = ["", "# Ring from declaration, name or entry evidence:"]
        lines.extend(self._lines(ringed, lambda v: v.ring or ""))
        lines.extend(("", "# Conflicts:"))
        lines.extend(self._lines(clash, lambda _: "CONFLICT"))
        lines.extend(("", "# Unclassified:"))
        lines.extend(self._lines(free, lambda _: "unclassified"))
        lines.extend(("", self._summary(ringed, clash, free)))
        return lines

    def _lines(self, names: list[str], label: Callable[[Verdict], str]) -> list[str]:
        if not names:
            return ["#   none"]
        return [
            f"#   {SafeText.comment(n)}: {label(self._verdicts[n])} "
            f"({SafeText.comment(self._verdicts[n].why)})"
            for n in names
        ]

    def _summary(self, ringed: list[str], clash: list[str], free: list[str]) -> str:
        named = sum(1 for n in ringed if self._verdicts[n].intended)
        return (
            f"# Summary: {named} of {len(self._modules)} modules ring-assigned from "
            f"a declaration or name, {len(ringed) - named} from entry evidence, "
            f"{len(clash)} conflicts, {len(free)} unclassified."
        )
