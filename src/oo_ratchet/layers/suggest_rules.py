"""The ring rules: entry, then adapters, then application, then domain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

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
       ``open``).
    3. ``application``: defines a ``Protocol``, imports no IO, and an adapter
       imports it.
    4. ``domain``: imports no IO and no entry or adapter module.

    A module that matches an outer ring and an inner one takes the outer ring
    and names the others in ``also``. A module that matches no rule (it imports
    an entry or adapter module but no IO) is left unclassified, not guessed.
    """

    _facts: tuple[ModuleFacts, ...]

    def __new__(cls, facts: list[ModuleFacts]) -> Self:
        self = super().__new__(cls)
        self._facts = tuple(facts)
        return self

    def verdicts(self) -> dict[str, Verdict]:
        """Return a verdict for every module, by name."""
        outer = {f.name: v for f in self._facts if (v := self._outer(f)) is not None}
        adapters = {n for n, v in outer.items() if v.ring == "adapters"}
        importers: dict[str, set[str]] = {}
        for fact in self._facts:
            for target in fact.imports:
                importers.setdefault(target, set()).add(fact.name)
        return {
            f.name: outer.get(f.name) or self._inner(f, set(outer), adapters, importers)
            for f in self._facts
        }

    @staticmethod
    def _outer(fact: ModuleFacts) -> Verdict | None:
        io = f"imports IO: {', '.join(fact.io)}"
        if fact.entry:
            also = (f"adapters ({io})",) if fact.io else ()
            return Verdict("entry", ", ".join(fact.entry), also)
        return Verdict("adapters", io) if fact.io else None

    @staticmethod
    def _inner(
        fact: ModuleFacts,
        outer: set[str],
        adapters: set[str],
        importers: dict[str, set[str]],
    ) -> Verdict:
        blocked = sorted(set(fact.imports) & outer)
        if blocked:
            why = f"imports adapters or entry: {', '.join(blocked)}; no IO"
            return Verdict(None, why)
        proto = ", ".join(fact.protocols)
        named = sorted(importers.get(fact.name, set()) & adapters)
        if proto and named:
            why = f"defines Protocol {proto}, no IO, imported by {', '.join(named)}"
            return Verdict("application", why)
        if proto:
            why = f"defines Protocol {proto} but no adapter imports it; no IO"
            return Verdict("domain", why)
        return Verdict("domain", "no IO, no adapter imports")
