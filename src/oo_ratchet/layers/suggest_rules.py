"""The ring rules: entry, then adapters, then application, then domain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Self

from .suggest_facts import ModuleFacts


@dataclass(frozen=True, slots=True)
class Verdict:
    """A module's suggested ring (``None`` when unclassifiable) and why."""

    ring: str | None
    why: str
    also: tuple[str, ...] = ()


class RingRules:
    """Classify modules; the first rule that matches wins.

    1. ``entry``: imports argparse or typer, or is a console-script target.
    2. ``adapters``: imports IO (the design check's ``DomainIO`` list, or a bare
       ``open``), and imports no ``entry`` module.
    3. ``application``: defines a ``Protocol``, imports no IO, and an adapter
       imports it.
    4. ``domain``: imports no IO.

    A module that matches an outer ring and an inner one takes the outer ring
    and names the others in ``also``. The gate lets ``domain`` import only
    ``domain`` and ``application`` import only ``application`` and ``domain``,
    so a table must not put a module where its imports are refused. After the
    rules, any ``domain`` or ``application`` module that imports a module of a
    ring it may not, or an unclassified module, is itself unclassified; that
    repeats until nothing changes. Shadowed modules and modules with an
    unresolvable relative import are unclassified from the start.
    """

    ALLOWED: ClassVar[dict[str, frozenset[str]]] = {
        "domain": frozenset({"domain"}),
        "application": frozenset({"application", "domain"}),
    }
    _facts: tuple[ModuleFacts, ...]

    def __new__(cls, facts: list[ModuleFacts]) -> Self:
        self = super().__new__(cls)
        self._facts = tuple(facts)
        return self

    def verdicts(self) -> dict[str, Verdict]:
        """Return a verdict for every module, by name."""
        result = self._first_pass()
        names = {f.name for f in self._facts}
        while self._demote(result, names):
            pass
        return result

    def _first_pass(self) -> dict[str, Verdict]:
        importers = self._importers()
        entries = self._entries(importers)
        outer = {f.name: self._outer(f, entries, importers) for f in self._facts}
        adapters = {n for n, v in outer.items() if v and v.ring == "adapters"}
        return {
            f.name: outer[f.name] or self._inner(f, importers, adapters)
            for f in self._facts
        }

    def _importers(self) -> dict[str, set[str]]:
        found: dict[str, set[str]] = {}
        for fact in self._facts:
            for target in fact.imports:
                found.setdefault(target, set()).add(fact.name)
        return found

    def _entries(self, importers: dict[str, set[str]]) -> set[str]:
        """Return the entry modules; the root is one only if just entry imports it."""
        found = {f.name for f in self._facts if not f.forced and f.entry and not f.root}
        roots = (f.name for f in self._facts if f.root and not f.forced)
        found.update(r for r in roots if not importers.get(r, set()) - found)
        return found

    @classmethod
    def _outer(
        cls, fact: ModuleFacts, entries: set[str], importers: dict[str, set[str]]
    ) -> Verdict | None:
        if fact.forced:
            return Verdict(None, fact.forced)
        if fact.root and fact.name not in entries:
            named = ", ".join(sorted(importers[fact.name] - entries))
            why = f"package root imported by non-entry {named}; only entry may"
            return Verdict(None, why)
        if fact.entry:
            io = f"adapters (imports IO: {', '.join(fact.io)})"
            return Verdict("entry", ", ".join(fact.entry), (io,) if fact.io else ())
        return cls._adapter(fact, entries) if fact.io else None

    @staticmethod
    def _adapter(fact: ModuleFacts, entries: set[str]) -> Verdict:
        io = f"imports IO: {', '.join(fact.io)}"
        blocked = sorted(set(fact.imports) & entries)
        if not blocked:
            return Verdict("adapters", io)
        why = f"{io}; imports entry {', '.join(blocked)}, which adapters may not"
        return Verdict(None, why)

    @staticmethod
    def _inner(
        fact: ModuleFacts, importers: dict[str, set[str]], adapters: set[str]
    ) -> Verdict:
        proto = ", ".join(fact.protocols)
        named = sorted(importers.get(fact.name, set()) & adapters)
        if proto and named:
            why = f"defines Protocol {proto}, no IO, imported by {', '.join(named)}"
            return Verdict("application", why)
        if proto:
            why = f"defines Protocol {proto} but no adapter imports it; no IO"
            return Verdict("domain", why)
        return Verdict("domain", "no IO, no adapter imports")

    def _demote(self, result: dict[str, Verdict], names: set[str]) -> bool:
        """Unclassify the modules whose imports their ring refuses; report any."""
        changed = False
        for fact in self._facts:
            why = self._refusal(fact, result, names)
            if why is not None:
                result[fact.name] = Verdict(None, why)
                changed = True
        return changed

    @staticmethod
    def _refused(
        fact: ModuleFacts,
        allowed: frozenset[str],
        result: dict[str, Verdict],
        names: set[str],
    ) -> list[str]:
        known = [t for t in fact.imports if t in names]
        return sorted(
            f"{t} ({result[t].ring or 'unclassified'})"
            for t in known
            if result[t].ring not in allowed
        )

    def _refusal(
        self, fact: ModuleFacts, result: dict[str, Verdict], names: set[str]
    ) -> str | None:
        ring = result[fact.name].ring
        if ring not in self.ALLOWED:
            return None
        bad = self._refused(fact, self.ALLOWED[ring], result, names)
        if not bad:
            return None
        allowed = " or ".join(sorted(self.ALLOWED[ring]))
        return f"{ring} may import only {allowed}; imports {', '.join(bad)}"
