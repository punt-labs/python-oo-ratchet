"""The ring rules: declared or named intent, checked against the import evidence."""

from __future__ import annotations

from dataclasses import replace
from typing import ClassVar, Self

from .ring_intent import Intent, RingIntent
from .ring_reach import IoReach
from .suggest_model import ModuleFacts, Verdict


class RingRules:
    """Give each module a ring from intent, a conflict, or no ring.

    Intent comes, in order, from a declaration (a module-level ``__ring__``
    string, then the existing fixed-form ``[tool.oo-ratchet.layers]`` table)
    and then a package-name convention. Import evidence never creates a ring
    except one: a module that imports ``argparse`` or ``typer``, or is a
    console-script target, is ``entry``.

    Evidence can only refuse intent. A module whose intent is ``domain`` but
    that reaches IO, directly or through the modules it imports, is a
    conflict, as is one whose intent disagrees with its entry evidence. After
    that, any module of a ring that may import only some rings (``domain``
    only ``domain``; ``application`` only ``application`` and ``domain``;
    ``adapters`` not ``entry``) that imports a module of another ring is a
    conflict, and a ``domain`` or ``application`` module that imports a module
    with no ring has none itself. That repeats until nothing changes. A module
    with no intent and no entry evidence has no ring, with its evidence.
    Shadowed modules and modules with an unresolvable relative import have no
    ring either.
    """

    ALLOWED: ClassVar[dict[str, frozenset[str]]] = {
        "domain": frozenset({"domain"}),
        "application": frozenset({"application", "domain"}),
        "adapters": frozenset({"adapters", "application", "domain"}),
    }
    _facts: tuple[ModuleFacts, ...]
    _intent: RingIntent
    _package: str

    def __new__(
        cls, facts: list[ModuleFacts], intent: RingIntent, package: str
    ) -> Self:
        self = super().__new__(cls)
        self._facts = tuple(facts)
        self._intent = intent
        self._package = package
        return self

    def verdicts(self) -> dict[str, Verdict]:
        """Return a verdict for every module, by name."""
        importers = self._importers()
        entries = self._entries(importers)
        reach = IoReach(self._facts)
        result = {
            f.name: self._first(f, entries, importers, reach) for f in self._facts
        }
        names = set(result)
        while self._demote(result, names):
            pass
        return result

    def _importers(self) -> dict[str, set[str]]:
        found: dict[str, set[str]] = {}
        for fact in self._facts:
            for target in fact.imports:
                found.setdefault(target, set()).add(fact.name)
        return found

    def _entries(self, importers: dict[str, set[str]]) -> set[str]:
        """Return the entry modules; the root is one only if just entry imports it."""
        found = {f.name for f in self._facts if f.evidenced()}
        roots = (f.name for f in self._facts if f.root and not f.forced)
        found.update(r for r in roots if not importers.get(r, set()) - found)
        return found

    def _first(
        self,
        fact: ModuleFacts,
        entries: set[str],
        importers: dict[str, set[str]],
        reach: IoReach,
    ) -> Verdict:
        if fact.forced:
            return Verdict(None, fact.forced)
        if fact.root:
            return self._root(fact, entries, importers)
        intent = self._intent.of(fact, self._package)
        chain = reach.chain(fact.name)
        if intent is None:
            return self._unintended(fact, chain)
        if intent.ring is None:
            return Verdict(None, intent.source)
        return self._intended(fact, intent, chain)

    @staticmethod
    def _root(
        fact: ModuleFacts, entries: set[str], importers: dict[str, set[str]]
    ) -> Verdict:
        if fact.name in entries:
            return Verdict("entry", fact.entry_why())
        named = ", ".join(sorted(importers[fact.name] - entries))
        return Verdict(
            None, f"package root imported by non-entry {named}; only entry may"
        )

    @staticmethod
    def _evidence(chain: str | None) -> str:
        return f"reaches IO: {chain}" if chain else "reaches no IO"

    @classmethod
    def _unintended(cls, fact: ModuleFacts, chain: str | None) -> Verdict:
        if fact.entry:
            return Verdict("entry", fact.entry_why())
        why = "no declaration or package name convention"
        return Verdict(None, f"{why}; {cls._evidence(chain)}")

    @classmethod
    def _intended(cls, fact: ModuleFacts, intent: Intent, chain: str | None) -> Verdict:
        ring = intent.ring
        if fact.entry and ring != "entry":
            why = f"{intent.source} says {ring}, but entry evidence: "
            return Verdict(None, why + ", ".join(fact.entry), conflict=True)
        if ring == "domain" and chain:
            why = f"{intent.source} says domain, but {cls._evidence(chain)}"
            return Verdict(None, why, conflict=True)
        return Verdict(ring, f"{intent.source}; {cls._evidence(chain)}", intended=True)

    def _demote(self, result: dict[str, Verdict], names: set[str]) -> bool:
        """Take the ring from each module whose imports its ring refuses."""
        changed = False
        for fact in self._facts:
            refusal = self._refusal(fact, result, names)
            if refusal is not None:
                result[fact.name] = replace(
                    refusal, why=f"{result[fact.name].why}; {refusal.why}"
                )
                changed = True
        return changed

    def _refusal(
        self, fact: ModuleFacts, result: dict[str, Verdict], names: set[str]
    ) -> Verdict | None:
        ring = result[fact.name].ring
        if ring not in self.ALLOWED:
            return None
        allowed = self.ALLOWED[ring]
        ringed, bare = self._refused(fact, allowed, result, names)
        may = f"{ring} may import only {' or '.join(sorted(allowed))}"
        if ringed:
            edge = f"{fact.name} -> {ringed[0]} ({result[ringed[0]].ring})"
            return Verdict(None, f"conflict {edge}; {may}", conflict=True)
        if bare and ring != "adapters":
            return Verdict(None, f"{may}; imports unclassified {', '.join(bare)}")
        return None

    @staticmethod
    def _refused(
        fact: ModuleFacts,
        allowed: frozenset[str],
        result: dict[str, Verdict],
        names: set[str],
    ) -> tuple[list[str], list[str]]:
        """Return the imports of a refused ring, and those with no ring at all."""
        refused = [
            t for t in fact.imports if t in names and result[t].ring not in allowed
        ]
        ringed = sorted(t for t in refused if result[t].ring)
        return ringed, sorted(t for t in refused if not result[t].ring)
