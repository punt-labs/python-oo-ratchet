"""The total-count operations over in-memory ports: no git, no filesystem."""

from __future__ import annotations

from dataclasses import dataclass, field

from oo_ratchet.core.adapters.tallyformats import TallyAuditFormat
from oo_ratchet.core.application.tallyops import (
    TallyCheck,
    TallyRebaseline,
    TallyRelax,
    TallyUpdate,
)
from oo_ratchet.core.application.tallyports import TallyPorts
from oo_ratchet.core.domain.ledgers import Ceiling, Ledger
from oo_ratchet.core.domain.tallies import Tally, TallyRecord
from oo_ratchet.core.domain.tallyverdicts import TallyVerdict
from oo_ratchet.core.domain.totals import FileRise, TotalReview

BASE = "base0"
TIP = "tip0"


def tally(**files: int) -> Tally:
    """A tally with ``noqa`` counts per file (``a_py`` names ``a.py``)."""
    by_file = {k.replace("_py", ".py"): {"noqa": n} for k, n in files.items()}
    return Tally({"noqa": sum(files.values())}, by_file)


@dataclass
class FakeHistory:
    refs: dict[str | None, str] = field(default_factory=lambda: {None: BASE})
    tallies: dict[str, Tally | None] = field(default_factory=dict)
    ledgers: dict[str, Ledger | None] = field(default_factory=dict)
    adopted: set[str] = field(default_factory=set)

    def resolve(self, ref: str | None) -> str | None:
        return self.refs.get(ref)

    def tally_at(self, ref: str) -> Tally | None:
        return self.tallies.get(ref)

    def adopted_at(self, ref: str) -> bool:
        return ref in self.adopted

    def ledger_at(self, ref: str) -> Ledger | None:
        return self.ledgers.get(ref)

    def head(self) -> str | None:
        return "abc1234"


@dataclass
class FakeStore:
    saved: Tally | None = None
    recorded: int | None = None

    @property
    def path(self) -> str:
        return "baseline.json"

    def exists(self) -> bool:
        return self.recorded is not None

    def total(self) -> int:
        return self.recorded or 0

    def save(self, tally: Tally) -> None:
        self.saved = tally
        self.recorded = tally.total


@dataclass
class FakeLedger:
    held: Ledger = field(default_factory=Ledger)

    @property
    def path(self) -> str:
        return "ledger.json"

    def ledger(self) -> Ledger:
        return self.held

    def add(self, file: str, ceiling: int, justify: str) -> None:
        self.held = Ledger(
            {**self.held.entries, file: Ceiling(file, ceiling, justify, "t")}
        )


@dataclass
class FakeAudit:
    records: list[TallyRecord] = field(default_factory=list)

    def append(self, record: TallyRecord) -> None:
        self.records.append(record)


@dataclass
class World:
    history: FakeHistory = field(default_factory=FakeHistory)
    store: FakeStore = field(default_factory=FakeStore)
    ledger: FakeLedger = field(default_factory=FakeLedger)
    audit: FakeAudit = field(default_factory=FakeAudit)

    @property
    def ports(self) -> TallyPorts:
        return TallyPorts(self.history, self.store, self.ledger, self.audit)


def check(
    w: World, now: Tally, *, tripwire: bool = False, require: bool = True
) -> TallyVerdict:
    return TallyCheck(w.ports).run(
        now, base_ref=None, require_base=require, tripwire=tripwire
    )


def test_rise_is_a_regression_naming_the_file() -> None:
    w = World()
    w.history.tallies[BASE] = tally(a_py=1)
    verdict = check(w, tally(a_py=3))
    assert [f.kind for f in verdict.failures] == ["suppression-increase"]
    assert verdict.totals == TotalReview(1, 3, 0, (FileRise("a.py", 2, 1, 3),))


def test_reduction_and_steady_pass() -> None:
    w = World()
    w.history.tallies[BASE] = tally(a_py=2)
    assert check(w, tally(a_py=1)).passed
    assert check(w, tally(a_py=2)).passed


def test_a_ceiling_covers_a_rise_up_to_it_and_never_below_the_base() -> None:
    w = World()
    w.history.tallies[BASE] = tally(a_py=4)
    w.ledger.add("a.py", 6, "needed")
    assert check(w, tally(a_py=6)).passed
    assert not check(w, tally(a_py=7)).passed
    w.ledger.add("a.py", 2, "below the base")
    assert check(w, tally(a_py=4)).passed


def test_a_ceiling_the_base_ledger_carries_is_retired() -> None:
    w = World()
    w.history.tallies[BASE] = tally(a_py=1)
    w.ledger.add("a.py", 3, "needed")
    w.history.ledgers[BASE] = w.ledger.held
    verdict = check(w, tally(a_py=3))
    assert not verdict.passed
    assert verdict.totals is not None
    assert verdict.totals.waived == 0


def test_unresolved_base_bootstraps_only_without_a_baseline() -> None:
    w = World()
    w.history.refs = {}
    assert [f.kind for f in check(w, tally(), require=True).failures] == [
        "base-unresolvable"
    ]
    assert check(w, tally(), require=False).passed
    w.store.recorded = 1
    assert [f.kind for f in check(w, tally(), require=False).failures] == ["base-stale"]


def test_base_without_the_source_tree() -> None:
    w = World()
    w.history.tallies[BASE] = None
    assert check(w, tally()).passed  # no tip: first adoption
    assert [f.kind for f in check(w, tally(), tripwire=True).failures] == [
        "tripwire-no-baseline"
    ]
    w.history.refs["origin/main"] = TIP
    w.history.adopted.add(TIP)
    assert [f.kind for f in check(w, tally()).failures] == ["base-predates-baseline"]


def test_update_never_loosens_and_audits_what_it_writes() -> None:
    w = World()
    update = TallyUpdate(w.ports)
    first = update.run(tally(a_py=5))  # first adoption bootstraps
    assert first.passed and first.verdict.written == ("baseline.json",)
    refused = update.run(tally(a_py=6))
    assert [f.kind for f in refused.failures] == ["raise-refused"]
    assert refused.totals == TotalReview(5, 6)
    assert w.store.saved == tally(a_py=5)
    assert update.run(tally(a_py=4)).passed
    assert [r.kind for r in w.audit.records] == ["update", "update"]


def test_relax_needs_a_justification_a_base_and_a_rise() -> None:
    w = World()
    w.history.tallies[BASE] = tally(a_py=1)
    relax = TallyRelax(w.ports)

    def run(now: Tally, justify: str = "why", file: str = "a.py") -> list[str]:
        verdict = relax.run(
            now, target="pkg", base_ref=None, file=file, justify=justify
        )
        return [f.kind for f in verdict.failures]

    assert run(tally(a_py=2), justify=" ") == ["blank-justification"]
    assert run(tally(a_py=1)) == ["nothing-to-relax"]
    assert run(tally(a_py=2), file="b.py") == ["nothing-to-relax"]
    w.history.tallies[BASE] = None
    assert run(tally(a_py=2)) == ["relax-absent-base"]
    w.history.refs = {}
    assert run(tally(a_py=2)) == ["relax-no-base"]
    assert w.audit.records == []


def test_relax_writes_the_ceiling_and_the_audit_record() -> None:
    w = World()
    w.history.tallies[BASE] = tally(a_py=1)
    verdict = TallyRelax(w.ports).run(
        tally(a_py=3), target="pkg", base_ref=None, file="a.py", justify="why"
    )
    assert verdict.verdict.written == ("ledger.json",)
    assert w.ledger.held.ceiling("a.py") == 3
    assert w.audit.records == [
        TallyRecord(
            "relaxed", file="a.py", before=1, after=3, reason="why", commit="abc1234"
        )
    ]


def test_rebaseline_raises_the_baseline_with_a_reason() -> None:
    w = World()
    rebaseline = TallyRebaseline(w.ports)
    assert [
        f.kind for f in rebaseline.run(tally(), reason=" ", source=None).failures
    ] == ["blank-reason"]
    assert rebaseline.run(tally(a_py=1), reason="r", source="PL-1").passed
    assert rebaseline.run(tally(a_py=9), reason="grow", source=None).passed
    first, second = w.audit.records
    assert (first.before, first.total, first.source) == (None, 1, "PL-1")
    assert (second.before, second.total) == (1, 9)


def test_rebased_moves_source_keys_and_keeps_pattern_keys() -> None:
    scanned = Tally(
        {"noqa": 2, "per_file_ignores": 3},
        {"/tmp/x/pkg/a.py": {"noqa": 2}, "pkg/a.py": {"per_file_ignores": 3}},
    )
    moved = scanned.rebased("/tmp/x/", "")
    assert moved.by_file == {"pkg/a.py": {"noqa": 2, "per_file_ignores": 3}}
    assert moved.total == scanned.total


def test_audit_lines_keep_each_kinds_key_order() -> None:
    update = TallyRecord("update", 2, {"noqa": 2})
    assert TallyAuditFormat.encode(update, "T") == (
        '{"ts":"T","total":2,"by_category":{"noqa":2}}\n'
    )
    relaxed = TallyRecord(
        "relaxed", file="a.py", before=1, after=2, reason="r", commit="c"
    )
    assert TallyAuditFormat.encode(relaxed, "T") == (
        '{"ts":"T","verdict":"relaxed","file":"a.py","before":1,"after":2,'
        '"reason":"r","commit":"c"}\n'
    )
    rebase = TallyRecord(
        "rebaseline", 3, {"noqa": 3}, reason="r", source="s", commit="c"
    )
    assert TallyAuditFormat.encode(rebase, "T") == (
        '{"ts":"T","verdict":"rebaseline","before":null,"total":3,'
        '"by_category":{"noqa":3},"reason":"r","source":"s","commit":"c"}\n'
    )
