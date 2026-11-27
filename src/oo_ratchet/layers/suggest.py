"""``layers --suggest``: print a starter ring table for a human to review."""

from __future__ import annotations

from typing import Self

from oo_ratchet.core.domain.exits import Outcome
from oo_ratchet.core.domain.layer_table import LayerTable
from oo_ratchet.core.domain.modules import ModuleIndex
from oo_ratchet.source_set import Source, SourceSet

from .ring_intent import RingIntent
from .scan import LayersScanError
from .suggest_facts import ConsoleScripts, PackageFacts, SuggestNames
from .suggest_lists import RingLists
from .suggest_rules import RingRules
from .suggest_table import RingTable

NO_PYPROJECT = "# No pyproject.toml was found: console scripts were not read."


class Suggestion:
    """Propose a ring for each module of a package from declared or named intent.

    Reads the package and the nearest pyproject's ``[project.scripts]``,
    ``[tool.oo-ratchet.suggest]`` and fixed-form layers table, if any. It
    returns text only and writes no file.
    """

    _src: Source
    _lists: RingLists
    _scripts: bool

    def __new__(cls, src: Source) -> Self:
        self = super().__new__(cls)
        self._src = src
        index = cls._index(src)
        anchor = SourceSet(src).config_anchor
        nearest = LayerTable.nearest(anchor)
        scripts = ConsoleScripts(nearest)
        facts = PackageFacts(index, scripts).all()
        if not any("." in fact.name for fact in facts):
            raise LayersScanError(f"no modules to check under {src}")
        table = LayerTable.ordered(LayerTable.load(anchor))
        intent = RingIntent(table, SuggestNames(nearest).table)
        verdicts = RingRules(facts, intent, index.package_name).verdicts()
        self._lists = RingLists(verdicts, index.package_name)
        self._scripts = scripts.found
        return self

    @staticmethod
    def _index(src: Source) -> ModuleIndex:
        SourceSet(src).require_package(LayersScanError)
        index = ModuleIndex(SourceSet(src))
        if index.skipped:
            names = ", ".join(sorted(str(p) for p in index.skipped))
            raise LayersScanError(f"cannot read or parse: {names}")
        return index

    def outcome(self) -> Outcome:
        """Return the table and the reasons; the exit code is always 0."""
        lists = self._lists
        table = RingTable(list(lists.modules), lists.rings()).render()
        missing = () if self._scripts else (NO_PYPROJECT,)
        return Outcome.passed(*lists.header(), *missing, *table, *lists.notes())
