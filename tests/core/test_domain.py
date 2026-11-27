"""Domain types of the shared core: immutable data, no IO."""

from __future__ import annotations

import dataclasses

import pytest

from oo_ratchet.core.domain.records import AuditRecord
from oo_ratchet.core.domain.scores import BaselineRow, Score
from oo_ratchet.core.domain.verdicts import FileReview, Review, Verdict, Waiver


def test_score_becomes_baseline_row() -> None:
    score = Score("a.py", {"avg_params": 2.0})
    assert BaselineRow.of(score) == BaselineRow("a.py", {"avg_params": 2.0})


def test_score_is_immutable() -> None:
    score = Score("a.py", {})
    with pytest.raises(dataclasses.FrozenInstanceError):
        score.path = "b.py"  # type: ignore[misc]


def test_waiver_is_a_path_metric_pair() -> None:
    assert Waiver("a.py", "avg_params") == ("a.py", "avg_params")


def test_review_passes_on_improvement() -> None:
    improved = FileReview("a.py", improved=True, base_present=True)
    assert Review((improved,)).improvement_satisfied
    assert not Review((improved,)).has_regression


def test_waiver_exempts_improvement_gate() -> None:
    waived = FileReview("a.py", waived=("m",), base_present=True)
    assert Review((waived,)).improvement_satisfied


def test_review_reports_regressions() -> None:
    bad = FileReview("a.py", regressed=("m",), base_present=True)
    assert Review((bad,)).regressions == (("a.py", "m"),)


def test_verdict_passes_only_without_failures() -> None:
    assert Verdict.ok("fine").passed
    assert not Verdict.refused("regression", "a.py").passed


def test_waivable_audit_record_yields_waivers() -> None:
    deltas = {"a.py": {"m": [1.0, 2.0]}}
    assert AuditRecord(verdict="relaxed", deltas=deltas).waivers() == frozenset(
        {Waiver("a.py", "m")}
    )
    assert AuditRecord(verdict="pass", deltas=deltas).waivers() == frozenset()
