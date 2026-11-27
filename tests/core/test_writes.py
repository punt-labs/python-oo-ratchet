"""Update, Relax, RebaselineFiles and Rebaseline, against in-memory ports."""

from __future__ import annotations

from oo_ratchet.core.application.update import Update
from oo_ratchet.core.application.waive import Rebaseline, RebaselineFiles, Relax
from oo_ratchet.core.domain.changes import Diff
from oo_ratchet.core.domain.verdicts import Verdict

from .doubles import BASE, World, oo_policy

OLD = {"max_complexity": 10.0}
BETTER = {"max_complexity": 8.0}
WORSE = {"max_complexity": 12.0}


def world(current: dict[str, float], stored: dict[str, float] = OLD) -> World:
    w = World()
    w.history.baselines[BASE] = {"a.py": dict(OLD)}
    w.history.diff = Diff(frozenset({"a.py"}))
    w.source.scores = {"a.py": dict(current)}
    w.store.data = {"a.py": dict(stored)}
    return w


def update(w: World, *, require_base: bool = True) -> Verdict:
    return Update(*w.args(oo_policy())).run(
        base_ref=None, require_base=require_base, source="PL-1"
    )


def kinds(v: Verdict) -> list[str]:
    return [f.kind for f in v.failures]


def test_update_writes_an_improvement_and_audits_it() -> None:
    w = world(BETTER)
    v = update(w)
    assert v.passed
    assert v.improved == 1
    assert w.store.data == {"a.py": BETTER}
    rec = w.audit.log[-1]
    assert (rec.verdict, rec.files_improved, rec.source) == ("pass", 1, "PL-1")
    assert rec.deltas == {"a.py": {"max_complexity": [10.0, 8.0]}}
    assert rec.commit == "abc1234"


def test_update_refuses_a_regression_and_keeps_the_row() -> None:
    w = world(WORSE)
    v = update(w)
    assert kinds(v) == ["regression"]
    assert w.store.data == {"a.py": OLD}
    assert w.audit.log[-1].verdict == "fail"


def test_update_accepts_a_later_commit_giving_back_part_of_a_gain() -> None:
    # In-tree row holds an earlier gain (8); now 9: worse than in-tree, but
    # better than the merge base (10), so it is accepted.
    w = world({"max_complexity": 9.0}, stored=BETTER)
    assert update(w).passed
    assert w.store.data == {"a.py": {"max_complexity": 9.0}}


def test_update_backfills_missing_rows_without_inventing_gains() -> None:
    w = world(BETTER)
    w.source.scores["b.py"] = {"max_complexity": 3.0}
    v = update(w)
    assert v.written == ("b.py",)
    assert w.audit.log[-1].extra == {"backfilled": ["b.py"]}
    assert w.audit.log[-1].deltas == {"a.py": {"max_complexity": [10.0, 8.0]}}


def test_update_carries_a_rename_and_drops_the_source_row() -> None:
    w = World()
    w.history.baselines[BASE] = {"old.py": dict(OLD)}
    w.history.diff = Diff(frozenset({"new.py"}), {"new.py": "old.py"})
    w.source.scores = {"new.py": dict(BETTER)}
    w.store.data = {"old.py": dict(OLD)}
    v = update(w)
    assert v.passed
    assert w.store.data == {"new.py": BETTER}
    assert v.removed == ("old.py",)


def test_update_refuses_a_regressed_rename_and_keeps_the_carried_row() -> None:
    w = World()
    w.history.baselines[BASE] = {"old.py": dict(OLD)}
    w.history.diff = Diff(frozenset({"new.py"}), {"new.py": "old.py"})
    w.source.scores = {"new.py": dict(WORSE)}
    w.store.data = {"old.py": dict(OLD)}
    assert kinds(update(w)) == ["regression"]
    assert w.store.data == {"old.py": OLD}


def test_update_rewrites_a_reverted_file_whose_row_was_rewritten() -> None:
    w = world(OLD, stored=BETTER)
    w.history.diff = Diff()  # reverted: absent from the diff
    assert update(w).passed
    assert w.store.data == {"a.py": OLD}


def test_update_drops_the_row_of_a_vanished_file() -> None:
    w = world(BETTER)
    w.store.data["gone.py"] = dict(OLD)  # type: ignore[index]
    w.source.disk = {"a.py"}
    v = update(w)
    assert v.removed == ("gone.py",)
    assert w.store.data == {"a.py": BETTER}


def test_update_refuses_a_parse_error_and_keeps_its_row() -> None:
    w = world(BETTER)
    w.source.scores = {}
    w.source.broken = frozenset({"a.py"})
    v = update(w)
    assert kinds(v) == ["parse-refused"]
    assert w.store.data == {"a.py": OLD}


def test_update_fails_closed_without_a_base() -> None:
    w = world(BETTER)
    w.history.refs = {}
    assert kinds(update(w)) == ["base-unresolvable"]
    assert kinds(update(w, require_base=False)) == ["base-stale"]
    w.store.data = None
    assert update(w, require_base=False).passed
    assert w.store.data == {"a.py": BETTER}


def test_relax_records_the_loosening_and_a_waiver() -> None:
    w = world(WORSE)
    v = Relax(*w.args(oo_policy())).run("a.py", justify="why", source=None)
    assert v.passed
    assert w.store.data == {"a.py": WORSE}
    rec = w.audit.log[-1]
    assert rec.verdict == "relaxed"
    assert rec.reason == "why"
    assert rec.waivers()


def test_relax_refusals() -> None:
    relax = Relax(*world(WORSE).args(oo_policy()))
    assert kinds(relax.run("a.py", justify=" ", source=None)) == ["blank-justification"]
    assert kinds(relax.run("zz.py", justify="x", source=None)) == ["not-scored"]
    w = world(BETTER)
    assert kinds(Relax(*w.args(oo_policy())).run("a.py", justify="x", source=None)) == [
        "nothing-to-relax"
    ]
    w.store.data = {}
    assert kinds(Relax(*w.args(oo_policy())).run("a.py", justify="x", source=None)) == [
        "no-row"
    ]


def test_rebaseline_files_blesses_a_within_cap_regression() -> None:
    w = world({"max_complexity": 9.0}, stored=BETTER)
    v = RebaselineFiles(*w.args(oo_policy())).run(["./a.py"], reason="r", source=None)
    assert v.passed
    assert w.store.data == {"a.py": {"max_complexity": 9.0}}
    assert w.audit.log[-1].waivers()


def test_rebaseline_files_refuses_over_cap_and_regressed_per_file() -> None:
    w = world({"avg_params": 5.0}, stored={"avg_params": 4.5})
    w.source.scores["b.py"] = {"avg_params": 1.0}
    w.store.data["b.py"] = {"avg_params": 2.0}  # type: ignore[index]
    v = RebaselineFiles(*w.args(oo_policy())).run(
        ["a.py", "b.py", "nope.py"], reason="r", source=None
    )
    assert kinds(v) == ["refused"]
    assert len(v.failures[0].subjects) == 2
    assert v.written == ("b.py",)
    assert w.store.data["a.py"] == {"avg_params": 4.5}  # type: ignore[index]
    assert w.store.data["b.py"] == {"avg_params": 1.0}  # type: ignore[index]


def test_rebaseline_files_needs_a_reason() -> None:
    w = world(BETTER)
    v = RebaselineFiles(*w.args(oo_policy())).run(["a.py"], reason=" ", source=None)
    assert kinds(v) == ["blank-reason"]


def test_rebaseline_resets_everything_and_audits_removed_rows() -> None:
    w = world(WORSE)
    w.store.data["gone.py"] = dict(OLD)  # type: ignore[index]
    v = Rebaseline(*w.args(oo_policy())).run(source="s")
    assert v.passed
    assert w.store.data == {"a.py": WORSE}
    assert w.audit.log[-1].removed == ("gone.py",)
    assert w.audit.log[-1].verdict == "rebaseline"
