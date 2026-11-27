"""Check, update, relax and rebaseline for a gate that compares a total count."""

from __future__ import annotations

from typing import Self

from oo_ratchet.core.domain.tallies import Tally, TallyRecord
from oo_ratchet.core.domain.totals import TotalReview
from oo_ratchet.core.domain.verdicts import Failure, Verdict

from .bases import Bases
from .tallyports import TallyPorts


class TallyOperation:
    """An operation over a gate's ports; it is given the tree's measured count."""

    _ports: TallyPorts

    def __new__(cls, ports: TallyPorts) -> Self:
        self = super().__new__(cls)
        self._ports = ports
        return self


class TallyCheck(TallyOperation):
    """Compare the current total with a fresh count of the base source.

    The base side is a rescan of the base commit's real source, never the
    in-tree baseline file, so a stale file cannot turn an existing suppression
    into a new one.
    """

    def run(
        self, tally: Tally, *, base_ref: str | None, require_base: bool, tripwire: bool
    ) -> Verdict:
        """Return the verdict for the change from the base to the work tree."""
        history = self._ports.history
        bases = Bases(history.resolve, history.adopted_at, self._ports.store.exists)
        base = history.resolve(base_ref)
        if base is None:
            return bases.unresolved(require_base=require_base)
        base_tally = history.tally_at(base)
        if base_tally is None:
            return bases.undocumented(tripwire=tripwire)
        ledger = self._ports.ledger.ledger().surviving(history.ledger_at(base))
        review = TotalReview.of(base_tally, tally, ledger)
        failures = (Failure("suppression-increase"),) if review.increased else ()
        return Verdict(failures=failures, totals=review)


class TallyUpdate(TallyOperation):
    """Record the current counts as the baseline; never loosen it."""

    def run(self, tally: Tally) -> Verdict:
        """Write ``tally``; refuse a rise over the in-tree total.

        First adoption (no in-tree baseline) bootstraps.
        """
        store = self._ports.store
        if store.exists() and tally.total > store.total():
            review = TotalReview(store.total(), tally.total)
            return Verdict(failures=(Failure("raise-refused"),), totals=review)
        store.save(tally)
        record = TallyRecord("update", tally.total, tally.by_category)
        self._ports.audit.append(record)
        return Verdict(written=(store.path,), record=record)


class TallyRelax(TallyOperation):
    """Record an audited ceiling for one file at its current count."""

    def run(
        self,
        tally: Tally,
        *,
        target: str,
        base_ref: str | None,
        file: str,
        justify: str,
    ) -> Verdict:
        """Refuse without a justification, a base or a rise; else write the ceiling.

        A write never bootstraps: an unresolvable or absent base is a failure.
        """
        if not justify.strip():
            return Verdict.refused("blank-justification")
        history = self._ports.history
        base = history.resolve(base_ref)
        if base is None:
            return Verdict.refused("relax-no-base", repr(base_ref))
        base_tally = history.tally_at(base)
        if base_tally is None:
            return Verdict.refused("relax-absent-base", target, base)
        current, baseline = tally.file_total(file), base_tally.file_total(file)
        if current <= baseline:
            return Verdict.refused("nothing-to-relax", file)
        ledger = self._ports.ledger
        ledger.add(file, current, justify)
        record = TallyRecord(
            "relaxed",
            file=file,
            before=baseline,
            after=current,
            reason=justify,
            commit=history.head(),
        )
        self._ports.audit.append(record)
        return Verdict(written=(ledger.path,), record=record)


class TallyRebaseline(TallyOperation):
    """Reset the baseline to the current counts: the one audited raise."""

    def run(self, tally: Tally, *, reason: str, source: str | None) -> Verdict:
        """Write ``tally`` and audit it, whatever the old total."""
        if not reason.strip():
            return Verdict.refused("blank-reason")
        store = self._ports.store
        before = store.total() if store.exists() else None
        store.save(tally)
        record = TallyRecord(
            "rebaseline",
            tally.total,
            tally.by_category,
            before=before,
            reason=reason,
            source=source,
            commit=self._ports.history.head(),
        )
        self._ports.audit.append(record)
        return Verdict(written=(store.path,), record=record)
