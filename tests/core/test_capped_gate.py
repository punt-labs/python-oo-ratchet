"""What the coupling gate needs of the core: per-file targets, in-tree updates,
a bless judged at the base, a detailed rebaseline, and the coupling state files.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oo_ratchet.core.adapters.auditview import AuditView
from oo_ratchet.core.adapters.couplingformats import CouplingAuditFormat
from oo_ratchet.core.adapters.formats import AuditFormat
from oo_ratchet.core.adapters.scoredtree import ScoredTree
from oo_ratchet.core.application.blessbase import BlessBase
from oo_ratchet.core.application.pathtargets import PathTargets
from oo_ratchet.core.application.policy import GatePolicy
from oo_ratchet.core.application.update import Update
from oo_ratchet.core.application.waive import Rebaseline, RebaselineFiles
from oo_ratchet.core.domain.changes import Diff
from oo_ratchet.core.domain.errors import StateError
from oo_ratchet.core.domain.metrics import Metric
from oo_ratchet.core.domain.records import AuditRecord
from oo_ratchet.core.domain.scores import Measurement, Score
from oo_ratchet.core.domain.verdicts import Verdict

from .doubles import BASE, World

TABLE = {"efferent": ("<=", 10.0), "names": ("<=", 15.0)}
MAIN = (Metric("names", "<=", 100.0),)
CAP = (Metric("efferent", "<=", 20.0),)


def policy(**flags: bool) -> GatePolicy:
    targets = PathTargets((("__main__.py", MAIN),), {"hub.py": CAP})
    metrics = tuple(Metric(n, op, t) for n, (op, t) in TABLE.items())
    return GatePolicy(
        metrics,
        must_improve=False,
        absolute_targets=False,
        lock_rows=False,
        in_tree_only=flags.get("in_tree_only", True),
        detailed_refusals=True,
        targets=targets,
    )


def world(**scores: dict[str, float]) -> World:
    w = World()
    w.source.scores = {p.replace("_py", ".py"): m for p, m in scores.items()}
    return w


def test_a_suffix_rule_and_a_cap_replace_only_the_named_targets() -> None:
    p = policy()
    assert p.for_path("pkg/__main__.py").metric("names").target == 100.0
    assert p.for_path("pkg/__main__.py").metric("efferent").target == 10.0
    assert p.for_path("hub.py").metric("efferent").target == 20.0
    assert p.for_path("other.py") is p


def test_a_cap_wins_over_a_suffix_rule() -> None:
    both = PathTargets(
        (("main.py", (Metric("names", "<=", 100.0),)),),
        {"main.py": (Metric("names", "<=", 50.0),)},
    )
    base = (Metric("names", "<=", 15.0),)
    assert both.metrics_for("main.py", base)[0].target == 50.0


def test_a_refusal_names_the_value_and_the_target_it_broke() -> None:
    p = policy().for_path("hub.py")
    text = p.refusal({"efferent": 21.0, "names": 3.0}, ["efferent"])
    assert text == "efferent=21 fails <= 20 (over cap and regressed)"
    plain = GatePolicy(policy().metrics, detailed_refusals=False)
    assert plain.refusal({"efferent": 21.0}, ["efferent", "names"]) == (
        "efferent, names over cap and regressed"
    )


def test_a_metric_missing_from_the_recorded_row_is_not_a_regression() -> None:
    assert policy().regressed({"efferent": 99.0}, {"names": 1.0}) == []
    strict = GatePolicy(policy().metrics)
    assert strict.regressed({"efferent": 99.0}, {"names": 1.0}) == ["efferent"]


def test_an_in_tree_update_ignores_the_base_baseline_and_counts_new_files() -> None:
    w = world(a_py={"efferent": 5.0}, new_py={"efferent": 9.0})
    w.history.baselines[BASE] = {"a.py": {"efferent": 4.0}}  # tighter than in-tree
    w.history.diff = Diff(frozenset({"a.py", "new.py"}))
    w.store.data = {"a.py": {"efferent": 6.0}}
    verdict = Update(*w.args(policy())).run(
        base_ref=None, require_base=True, source=None
    )
    assert verdict.passed
    assert verdict.improved == 2  # a.py improved on the in-tree row; new.py is new
    assert w.store.data["a.py"] == {"efferent": 5.0}


def test_only_an_update_on_merge_base_rows_accepts_what_loosens_the_in_tree_row() -> (
    None
):
    """Worse than the in-tree row, better than the base row."""
    for in_tree_only, passes in ((True, False), (False, True)):
        w = world(a_py={"efferent": 7.0})
        w.history.baselines[BASE] = {"a.py": {"efferent": 8.0}}
        w.history.diff = Diff(frozenset({"a.py"}))
        w.store.data = {"a.py": {"efferent": 6.0}}
        verdict = Update(*w.args(policy(in_tree_only=in_tree_only))).run(
            base_ref=None, require_base=True, source=None
        )
        assert verdict.passed is passes


def test_a_bless_is_judged_by_the_row_at_the_base_and_drops_a_renamed_row() -> None:
    w = world(hub_py={"efferent": 12.0})
    w.store.data = {"old.py": {"efferent": 12.0}, "hub.py": {"efferent": 12.0}}
    base = BlessBase({"old.py": {"efferent": 11.0}}, {"hub.py": "old.py"})
    verdict = RebaselineFiles(*w.args(policy())).run(
        ["hub.py", "./hub.py"], reason="r", source=None, base=base
    )
    assert verdict.passed
    assert verdict.written == ("hub.py",)  # named twice, written once
    assert "old.py" not in (w.store.data or {})
    assert w.audit.log[-1].files_scored == 1


def test_a_bless_over_the_cap_and_worse_than_the_base_is_refused_with_detail() -> None:
    w = world(hub_py={"efferent": 21.0})
    w.store.data = {"hub.py": {"efferent": 21.0}}  # in-tree already locked
    base = BlessBase({"hub.py": {"efferent": 18.0}})
    verdict = RebaselineFiles(*w.args(policy())).run(
        ["hub.py"], reason="r", source=None, base=base
    )
    assert verdict.failures[0].subjects == (
        "hub.py: efferent=21 fails <= 20 (over cap and regressed)",
    )
    assert verdict.written == ()


def test_the_base_a_bless_needs() -> None:
    w = World()
    w.history.refs = {None: BASE, BASE: BASE}
    w.history.baselines[BASE] = {}
    w.history.diff = Diff(renames={"b.py": "a.py"})
    bad = BlessBase.load(w.history, "nope", require_base=False)
    assert isinstance(bad, Verdict)
    assert bad.failures[0].kind == "bless-bad-ref"
    empty = BlessBase.load(w.history, BASE, require_base=True)
    assert isinstance(empty, Verdict)
    assert empty.failures[0].kind == "bless-no-base-baseline"
    found = BlessBase.load(w.history, BASE, require_base=False)
    assert isinstance(found, BlessBase)
    assert found.renames == {"b.py": "a.py"}
    w.history.refs = {}
    assert BlessBase.load(w.history, None, require_base=False) is None
    unresolved = BlessBase.load(w.history, None, require_base=True)
    assert isinstance(unresolved, Verdict)
    assert unresolved.failures[0].kind == "base-unresolvable"


def test_a_detailed_rebaseline_records_changes_gains_losses_and_the_reason() -> None:
    w = world(a_py={"efferent": 9.0}, b_py={"efferent": 3.0}, c_py={"efferent": 1.0})
    w.store.data = {
        "a.py": {"efferent": 8.0},
        "b.py": {"efferent": 4.0},
        "gone.py": {"efferent": 1.0},
    }
    verdict = Rebaseline(*w.args(policy())).run(source="s", reason=" why ", detail=True)
    record = w.audit.log[-1]
    assert verdict.passed
    assert record.reason == "why"
    assert record.deltas == {
        "a.py": {"efferent": [8.0, 9.0]},
        "b.py": {"efferent": [4.0, 3.0]},
        "c.py": {"efferent": [0.0, 1.0]},
    }
    assert (record.files_improved, record.files_regressed) == (1, 1)
    assert record.removed == ("gone.py",)


def test_a_plain_rebaseline_records_no_changes() -> None:
    w = world(a_py={"efferent": 9.0})
    w.store.data = {"a.py": {"efferent": 8.0}}
    Rebaseline(*w.args(policy())).run(source=None)
    record = w.audit.log[-1]
    assert (record.deltas, record.files_improved, record.files_regressed) == ({}, 0, 0)


def test_the_coupling_audit_line_always_has_a_reason_and_omits_empty_removed() -> None:
    record = AuditRecord(verdict="pass", files_scored=2, commit="abc1234")
    line = json.loads(CouplingAuditFormat.encode(record, "T"))
    assert list(line) == [
        "ts",
        "commit",
        "source",
        "files_scored",
        "files_improved",
        "files_regressed",
        "verdict",
        "reason",
        "deltas",
    ]
    assert line["reason"] is None
    shared = json.loads(AuditFormat.encode(record, "T"))
    assert "reason" not in shared
    assert shared["removed"] == []
    gone = AuditRecord(verdict="pass", removed=("b.py", "a.py"), extra={"x": 1})
    assert json.loads(CouplingAuditFormat.encode(gone, "T"))["removed"] == [
        "a.py",
        "b.py",
    ]


def test_a_scored_tree_names_a_file_by_any_spelling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n")
    tree = ScoredTree(tmp_path, Measurement((Score("pkg/a.py", {"m": 1.0}),)))
    monkeypatch.chdir(tmp_path / "pkg")
    assert tree.key("pkg/a.py") == "pkg/a.py"
    assert tree.key("./pkg/a.py") == "pkg/a.py"
    assert tree.key("a.py") == "pkg/a.py"  # relative to the working directory
    assert tree.key(str(tmp_path / "pkg" / "a.py")) == "pkg/a.py"
    assert tree.key("pkg/missing.py") == "pkg/missing.py"
    assert tree.exists("pkg/a.py")
    assert not tree.exists("pkg/b.py")


def test_the_audit_view_names_what_is_corrupt(tmp_path: Path) -> None:
    log = tmp_path / "audit.jsonl"
    view = AuditView(log, "coupling")
    assert view.lines() == ["No audit log found"]
    log.write_text('{"verdict":"pass","files_scored":2}\n\n')
    rows = view.lines()
    assert rows[-1].split() == ["?", "?", "2", "0", "0", "pass"]
    log.write_text("[1]\n")
    with pytest.raises(StateError, match=r"coupling audit log .*not an object"):
        view.lines()
    log.write_text("garbage\n")
    with pytest.raises(StateError, match="corrupt coupling audit log"):
        view.lines()


def test_an_audit_entry_of_odd_shape_waives_nothing_and_does_not_crash() -> None:
    text = "\n".join(
        [
            '{"verdict":"relaxed","deltas":[1,2]}',
            '{"verdict":"relaxed","deltas":{"a.py":"efferent"}}',
            '{"verdict":["relaxed"],"deltas":{"a.py":{"efferent":[1,2]}}}',
            '{"verdict":"relaxed","deltas":{"a.py":{"efferent":[1,2]}}}',
        ]
    )
    records = AuditFormat.decode(text)
    waivers = AuditRecord.waivers_since(records, None)
    assert [(w.path, w.metric) for w in waivers] == [("a.py", "efferent")]
