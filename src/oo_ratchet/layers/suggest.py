"""``layers --suggest``: print a starter ring table for a human to review."""

from __future__ import annotations

from typing import Self

from oo_ratchet.coupling.outcome import Outcome
from oo_ratchet.design.layer_table import LayerTable
from oo_ratchet.design.modules import ModuleIndex
from oo_ratchet.source_set import Source, SourceSet

from .scan import LayersScanError
from .suggest_facts import ConsoleScripts, PackageFacts
from .suggest_rules import RingRules, Verdict
from .suggest_table import RingTable

HEADER = (
    "# oo-ratchet layers --suggest {package}: a starting point, never applied.",
    "# Nothing was written. A wrong ring lets forbidden imports pass: review each",
    "# reason below, then copy the table into pyproject.toml yourself.",
    "# Rule order, first match wins: entry (argparse, typer, console script),",
    "# adapters (imports IO), application (defines a Protocol, no IO, imported by",
    "# an adapter), domain (no IO, no adapter or entry imports). A module that fits",
    "# none is listed as unclassified instead of guessed. The gate lets domain import",
    "# only domain and application import only application and domain, so a module",
    "# that imports a ring it may not (or an unclassified module) is unclassified too.",
    "# A glob such as pkg.sub.* also claims any module added later under that prefix.",
)
NO_PYPROJECT = "# No pyproject.toml was found: console scripts were not read."


class Suggestion:
    """Propose a ring for each module of a package from what it imports.

    Reads the package and the nearest pyproject's ``[project.scripts]``; it
    needs no layers table. It returns text only and writes no file.
    """

    _src: Source
    _verdicts: dict[str, Verdict]
    _modules: tuple[str, ...]
    _package: str
    _scripts: bool

    def __new__(cls, src: Source) -> Self:
        self = super().__new__(cls)
        self._src = src
        SourceSet(src).require_package(LayersScanError)
        index = ModuleIndex(src)
        if index.skipped:
            names = ", ".join(sorted(str(p) for p in index.skipped))
            raise LayersScanError(f"cannot read or parse: {names}")
        scripts = ConsoleScripts(LayerTable.nearest(src))
        facts = PackageFacts(index, scripts).all()
        if len(facts) < 2:
            raise LayersScanError(f"no modules to check under {src}")
        self._verdicts = RingRules(facts).verdicts()
        self._modules = tuple(sorted(self._verdicts))
        self._package = index.package_name
        self._scripts = scripts.found
        return self

    def outcome(self) -> Outcome:
        """Return the table and the reasons; the exit code is always 0."""
        rings = {n: v.ring for n, v in self._verdicts.items() if v.ring}
        table = RingTable(list(self._modules), rings).render()
        header = tuple(line.format(package=self._package) for line in HEADER)
        missing = () if self._scripts else (NO_PYPROJECT,)
        return Outcome.passed(*header, *missing, *table, *self._notes())

    def _notes(self) -> list[str]:
        lines = ["", "# Unclassified (assign by hand, then add to the table):"]
        unknown = [n for n in self._modules if self._verdicts[n].ring is None]
        lines.extend(f"# {n}: unclassified ({self._verdicts[n].why})" for n in unknown)
        if not unknown:
            lines.append("#   none")
        lines.extend(("", "# Reasons:"))
        placed = [n for n in self._modules if n not in unknown]
        lines.extend(self._reason(n) for n in placed)
        if not placed:
            lines.append("#   none")
        return lines

    def _reason(self, name: str) -> str:
        verdict = self._verdicts[name]
        text = f"# {name}: {verdict.ring} ({verdict.why})"
        if verdict.also:
            text += f"; rings it also matched: {', '.join(verdict.also)}"
        return text
