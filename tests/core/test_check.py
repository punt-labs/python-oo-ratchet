"""Check, run against in-memory ports."""

from __future__ import annotations

from oo_ratchet.core.application.check import Check
from oo_ratchet.core.domain.changes import Diff
from oo_ratchet.core.domain.records import AuditRecord
from oo_ratchet.core.domain.verdicts import Verdict

from .doubles import BASE, TIP, World, coupling_policy, oo_policy

WORSE = {"max_complexity": 12.0}
BETTER = {"max_complexity": 8.0}
BASE_ROW = {"max_complexity": 10.0}


def world(
    current: dict[str, float], base: dict[str, float] = BASE_ROW, *, intree: bool = True
) -> World:
    """One touched file ``a.py``: base row, in-tree row, current score."""
    w = World()
    w.history.baselines[BASE] = {"a.py": dict(base)}
    w.history.diff = Diff(frozenset({"a.py"}))
    w.source.scores = {"a.py": dict(current)}
    w.store.data = {"a.py": dict(current if intree else base)}
    return w


def check(w: World, **kw: bool | str | None) -> Verdict:
    return Check(*w.args(oo_policy())).run(
        base_ref=kw.pop("base_ref", None),  # type: ignore[arg-type]
        require_base=bool(kw.pop("require_base", True)),
        **kw,  # type: ignore[arg-type]
    )


def kinds(v: Verdict) -> list[str]:
    return [f.kind for f in v.failures]


def test_regression_is_caught() -> None:
    v = check(world(WORSE))
    assert kinds(v) == ["regression", "no-improvement"]
    assert v.failures[0].subjects == ("a.py: max_complexity",)


def test_improvement_is_credited() -> None:
    v = check(world(BETTER))
    assert v.passed
    assert v.note == "at least one metric improved, no regressions"


def test_unchanged_touched_file_fails_must_improve() -> None:
    assert kinds(check(world(BASE_ROW))) == ["no-improvement"]


def test_allow_no_improvement_waives_only_that_gate() -> None:
    assert check(world(BASE_ROW), allow_no_improvement=True).passed
    assert kinds(check(world(WORSE), allow_no_improvement=True)) == ["regression"]


def test_in_tree_row_must_match_the_scores() -> None:
    v = check(world(BETTER, intree=False))
    assert kinds(v) == ["stale-row"]


def test_audited_waiver_forgives_a_locked_regression() -> None:
    w = world(WORSE)
    w.audit.append(
        AuditRecord(verdict="relaxed", deltas={"a.py": {"max_complexity": [10, 12]}})
    )
    v = check(w)
    assert v.passed
    assert v.review is not None
    assert v.review.has_waiver


def test_waiver_already_in_the_base_log_is_history() -> None:
    w = world(WORSE)
    record = AuditRecord(
        verdict="relaxed", deltas={"a.py": {"max_complexity": [10, 12]}}
    )
    w.audit.append(record)
    w.history.audits[BASE] = (record,)
    assert kinds(check(w)) == ["regression", "no-improvement"]


def test_waiver_needs_the_in_tree_row_locked() -> None:
    w = world(WORSE, intree=False)
    w.audit.append(
        AuditRecord(verdict="relaxed", deltas={"a.py": {"max_complexity": [10, 12]}})
    )
    assert "regression" in kinds(check(w))


def test_reverted_file_with_rewritten_row_must_be_locked() -> None:
    w = world(BASE_ROW)
    w.history.diff = Diff()  # reverted: not in the diff
    w.store.data = {"a.py": BETTER}  # row still holds an earlier commit's gain
    assert kinds(check(w)) == ["stale-row"]


def test_untouched_change_passes() -> None:
    w = world(BASE_ROW)
    w.history.diff = Diff()
    assert check(w).passed


def test_rename_inherits_the_predecessor_row() -> None:
    w = World()
    w.history.baselines[BASE] = {"old.py": dict(BASE_ROW)}
    w.history.diff = Diff(frozenset({"new.py"}), {"new.py": "old.py"})
    w.source.scores = {"new.py": dict(WORSE)}
    w.store.data = {"new.py": dict(WORSE)}
    assert kinds(check(w)) == ["regression", "no-improvement"]


def test_new_file_must_meet_targets() -> None:
    w = World()
    w.history.baselines[BASE] = {"other.py": dict(BASE_ROW)}
    w.history.diff = Diff(frozenset({"new.py"}))
    w.source.scores = {"new.py": dict(WORSE)}
    w.store.data = {"new.py": dict(WORSE)}
    assert kinds(check(w)) == ["regression", "no-improvement"]


def test_parse_error_in_touched_file_fails() -> None:
    w = world(BETTER)
    w.source.broken = frozenset({"a.py"})
    assert kinds(check(w)) == ["parse-error"]


def test_unresolvable_base_fails_under_require_base() -> None:
    w = world(BETTER)
    w.history.refs = {}
    assert kinds(check(w)) == ["base-unresolvable"]
    assert kinds(check(w, require_base=False)) == ["base-stale"]
    w.store.data = None
    assert check(w, require_base=False).passed


def test_base_without_baseline_bootstraps_only_at_adoption() -> None:
    w = world(BETTER)
    w.history.baselines = {}
    w.history.refs = {None: BASE, "origin/main": TIP}
    assert check(w).passed
    w.history.baselines[TIP] = {"a.py": dict(BASE_ROW)}
    assert kinds(check(w)) == ["base-predates-baseline"]
    assert check(w, tripwire=True).passed


def test_empty_base_baseline_fails_under_require_base() -> None:
    w = world(BETTER)
    w.history.baselines[BASE] = {}
    assert kinds(check(w)) == ["base-empty"]


def test_regression_only_policy_holds_steady_and_flags_worse() -> None:
    w = world({"efferent_coupling": 9.0}, {"efferent_coupling": 9.0})
    run = Check(*w.args(coupling_policy())).run(base_ref=None, require_base=True)
    assert run.passed
    w.source.scores = {"a.py": {"efferent_coupling": 11.0}}
    run = Check(*w.args(coupling_policy())).run(base_ref=None, require_base=True)
    assert kinds(run) == ["regression"]


def test_regression_only_policy_reports_new_files_as_info() -> None:
    w = World()
    w.history.baselines[BASE] = {}
    w.history.diff = Diff(frozenset({"new.py"}))
    w.source.scores = {"new.py": {"efferent_coupling": 99.0}}
    run = Check(*w.args(coupling_policy())).run(base_ref=None, require_base=False)
    assert run.passed
