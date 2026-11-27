"""Reviews and metrics answer questions; callers do not read their fields."""

from __future__ import annotations

import pytest

from oo_ratchet.core.application.edgeports import Survey
from oo_ratchet.core.domain.layer_edges import Edge, Violation
from oo_ratchet.core.domain.metrics import Metric
from oo_ratchet.core.domain.verdicts import FileReview, Review


class TestFileReviewAnswers:
    """A file review says whether it earns the must-improve credit."""

    def test_tracked_file_earns_credit_by_improving(self) -> None:
        file = FileReview("a.py", improved=True, base_present=True)
        assert file.credits(tracked_present=True)

    def test_new_file_earns_credit_only_when_nothing_is_tracked(self) -> None:
        file = FileReview("new.py", new_passes=True)
        assert file.credits(tracked_present=False)
        assert not file.credits(tracked_present=True)

    def test_is_tracked_follows_the_base_row(self) -> None:
        assert FileReview("a.py", base_present=True).tracked
        assert not FileReview("a.py").tracked

    def test_review_gate_uses_the_answers(self) -> None:
        tracked = FileReview("a.py", base_present=True)
        fresh = FileReview("new.py", new_passes=True)
        assert not Review((tracked, fresh)).improvement_satisfied
        assert Review((fresh,)).improvement_satisfied


class TestMetricClassifies:
    """A metric judges a value against a base value."""

    @pytest.mark.parametrize(
        ("current", "base", "waived", "status"),
        [
            (1.0, 2.0, False, "IMPROVED"),
            (2.0, 2.0, False, "PASS"),
            (3.0, 2.0, False, "REGRESSED"),
            (3.0, 2.0, True, "RELAXED"),
            (10.0, None, False, "PASS"),
            (11.0, None, False, "REGRESSED"),
        ],
    )
    def test_status(
        self, current: float, base: float | None, waived: bool, status: str
    ) -> None:
        metric = Metric("max_complexity", "<=", 10)
        assert metric.classify(current, base, waived=waived) == status


class TestLayerScanAnswers:
    """A scan says what held edges and widening it has; callers do not dig."""

    def test_violation_describes_itself(self) -> None:
        violation = Violation(Edge("app.a", "app.b"), "domain", "adapters")
        assert violation.as_dict() == {
            "source": "app.a",
            "target": "app.b",
            "source_layer": "domain",
            "target_layer": "adapters",
        }

    def test_survey_no_longer_exposes_its_config_for_callers_to_judge(self) -> None:
        assert not hasattr(Survey, "under")
        assert not hasattr(Survey, "config")
        assert hasattr(Survey, "held_edges")
        assert hasattr(Survey, "widened_over")
