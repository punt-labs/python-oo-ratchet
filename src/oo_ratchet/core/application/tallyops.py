"""Check, update, relax and rebaseline for a gate that compares a total count."""

from __future__ import annotations

from typing import Self

from oo_ratchet.core.domain.tallies import Tally, TallyRecord
from oo_ratchet.core.domain.tallyverdicts import TallyVerdict
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

    @staticmethod
    def _refused(kind: str, *subjects: str) -> TallyVerdict:
        return TallyVerdict(Verdict.refused(kind, *subjects))

    @staticmethod
    def _written(path: str, record: TallyRecord) -> TallyVerdict:
        return TallyVerdict(Verdict.ok(written=(path,)), record=record)


class TallyCheck(TallyOperation):
    """Compare the current total with a fresh count of the base source.

    The base side is a rescan of the base commit's real source, never the
    in-tree baseline file, so a stale file cannot turn an existing suppression
    into a new one.
    """

    def run(
        self, tally: Tally, *, base_ref: str | None, require_base: bool, tripwire: bool
    ) -> TallyVerdict:
        """Return the verdict for the change from the base to the work tree."""
        history = self._ports.history
        bases = Bases(history, self._ports.store)
        base = history.resolve(base_ref)
        if base is None:
            return TallyVerdict(bases.unresolved(require_base=require_base))
        base_tally = history.tally_at(base)
        if base_tally is None:
            return TallyVerdict(bases.undocumented(tripwire=tripwire))
        ledger = self._ports.ledger.ledger().surviving(history.ledger_at(base))
        review = TotalReview.of(base_tally, tally, ledger)
        failures = (Failure("suppression-increase"),) if review.increased else ()
        return TallyVerdict(Verdict(failures=failures), totals=review)


class TallyUpdate(TallyOperation):
    """Record the current counts as the baseline; never loosen it."""

    def run(self, tally: Tally) -> TallyVerdict:
        """Write ``tally``; refuse a rise over the in-tree total.

        First adoption (no in-tree baseline) bootstraps.
        """
        store = self._ports.store
        if store.exists() and tally.total > store.total():
            review = TotalReview(store.total(), tally.total)
            return TallyVerdict(Verdict.refused("raise-refused"), totals=review)
        store.save(tally)
        record = TallyRecord("update", tally.total, tally.by_category)
        self._ports.audit.append(record)
        return self._written(store.path, record)


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
    ) -> TallyVerdict:
        """Refuse without a justification, a base or a rise; else write the ceiling.

        A write never bootstraps: an unresolvable or absent base is a failure.
        """
        if not justify.strip():
            return self._refused("blank-justification")
        history = self._ports.history
        base = history.resolve(base_ref)
        if base is None:
            return self._refused("relax-no-base", repr(base_ref))
        base_tally = history.tally_at(base)
        if base_tally is None:
            return self._refused("relax-absent-base", target, base)
        current, baseline = tally.file_total(file), base_tally.file_total(file)
        if current <= baseline:
            return self._refused("nothing-to-relax", file)
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
        return self._written(ledger.path, record)


class TallyRebaseline(TallyOperation):
    """Reset the baseline to the current counts: the one audited raise."""

    def run(self, tally: Tally, *, reason: str, source: str | None) -> TallyVerdict:
        """Write ``tally`` and audit it, whatever the old total."""
        if not reason.strip():
            return self._refused("blank-reason")
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
        return self._written(store.path, record)
