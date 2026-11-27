"""PL-1685: the OO gate does not push code into small, single-class modules.

The gate used to compare ``module_size`` and ``classes_per_module`` file by
file and fail on any growth, and required ``method_ratio`` and
``class_to_func_ratio`` floors. Together they rewarded splitting cohesive
code into tiny one-class modules and wrapping functions in stateless classes.
Module size is now an absolute ceiling only, and the class-count and ratio
metrics are not gated.
"""

from __future__ import annotations

import json
from typing import ClassVar

import pytest

from oo_ratchet.oo.apply import PlanApplier
from oo_ratchet.oo.baseline import Baseline
from oo_ratchet.oo.compare import FileReview
from oo_ratchet.oo.thresholds import Thresholds
from tests.test_oo_ratchet import GOOD, WORSE, GitFixture

pytestmark = pytest.mark.slow

# Between GOOD (complexity 1) and WORSE (complexity 3): one branch.
MIDDLE = GOOD.replace(
    '        return "pos"\n',
    '        if self._n > 0:\n            return "pos"\n        return "neg"\n',
)
assert MIDDLE != GOOD, "GOOD fixture drifted; MIDDLE no longer differs"

# GOOD plus one more simple method: more code lines, same complexity.
GROWN = (
    GOOD
    + """
    def describe(self) -> str:
        return f"widget {self._n}"
"""
)

# GOOD plus a second small class in the same module.
TWO_CLASSES = (
    GOOD
    + '''

class Gadget:
    """A gadget."""

    _w: Widget

    def __new__(cls, w: Widget) -> "Gadget":
        self = super().__new__(cls)
        self._w = w
        return self

    def label(self) -> str:
        return self._w.label()
'''
)

# A module whose public entry point is a plain function: no classes at all.
FUNCTION_MODULE = '''from __future__ import annotations


def quote(days: int) -> int:
    """Return the fee for a loan of ``days`` days."""
    return max(days, 0) * 2
'''


class TestThresholdTable:
    """The gate no longer rewards splitting or wrapping functions in classes."""

    @pytest.mark.parametrize(
        "metric", ["classes_per_module", "method_ratio", "class_to_func_ratio"]
    )
    def test_shape_metric_is_not_gated(self, metric: str) -> None:
        assert metric not in Thresholds.names()

    def test_module_size_ceiling_is_400(self) -> None:
        assert Thresholds.meets("module_size", 400)
        assert not Thresholds.meets("module_size", 401)

    def test_growth_under_ceiling_is_not_a_regression(self) -> None:
        # The lux case: a 29-line composition root grew to 39 lines.
        assert Thresholds.better_or_equal("module_size", 39, 29)
        assert not Thresholds.strictly_better("module_size", 29, 39)

    def test_growth_over_ceiling_is_a_regression(self) -> None:
        assert not Thresholds.better_or_equal("module_size", 451, 450)
        assert not Thresholds.better_or_equal("module_size", 401, 380)

    def test_shrinking_an_over_ceiling_module_is_an_improvement(self) -> None:
        assert Thresholds.strictly_better("module_size", 420, 450)
        assert Thresholds.strictly_better("module_size", 390, 450)

    def test_ceiling_boundary(self) -> None:
        assert Thresholds.better_or_equal("module_size", 400, 300)
        assert not Thresholds.strictly_better("module_size", 400, 300)
        assert Thresholds.strictly_better("module_size", 400, 401)
        assert not Thresholds.better_or_equal("module_size", 401, 400)


class TestUpdateRecords:
    def test_growth_under_ceiling_is_not_counted_as_an_improvement(self) -> None:
        deltas = {"sub/w.py": {"module_size": [9.0, 10.0]}}
        assert PlanApplier.improved_count(deltas) == 0

    def test_metric_missing_from_base_row_is_judged_by_target(self) -> None:
        entry = {"module_size": 5000.0, "avg_params": 1.0}
        assert PlanApplier.regressed(entry, {"avg_params": 2.0}) == ["module_size"]
        small = {"module_size": 50.0, "avg_params": 1.0}
        assert PlanApplier.regressed(small, {"avg_params": 2.0}) == []

    def test_refused_only_when_worse_than_every_comparison_row(self) -> None:
        entry = {"max_complexity": 2.0}
        assert PlanApplier.refusals(entry, [{"max_complexity": 1.0}]) == [
            "max_complexity"
        ]
        # Worse than the merge base but no worse than the in-tree (relaxed) row.
        rows = [{"max_complexity": 1.0}, {"max_complexity": 3.0}]
        assert PlanApplier.refusals(entry, rows) == []
        assert PlanApplier.refusals(entry, []) == []

    def test_a_real_improvement_is_counted(self) -> None:
        deltas = {"sub/w.py": {"module_size": [9.0, 10.0], "avg_params": [3.0, 2.0]}}
        assert PlanApplier.improved_count(deltas) == 1


class TestGateEndToEnd:
    """Drive the ratchet against a real git history."""

    def test_growing_a_small_module_passes(self, fx: GitFixture) -> None:
        fx.write("sub/w.py", GOOD)
        fx.snapshot("sub")
        base = fx.commit("base")
        fx.write("sub/w.py", GROWN)
        fx.snapshot("sub")
        fx.commit("grow")
        outcome = fx.ratchet().check(
            fx.scorer(), base_ref=base, require_base=True, allow_no_improvement=True
        )
        assert outcome.exit_code == 0, outcome.lines

    def test_second_class_in_a_module_passes(self, fx: GitFixture) -> None:
        fx.write("sub/w.py", GOOD)
        fx.snapshot("sub")
        base = fx.commit("base")
        fx.write("sub/w.py", TWO_CLASSES)
        fx.snapshot("sub")
        fx.commit("second class")
        outcome = fx.ratchet().check(
            fx.scorer(), base_ref=base, require_base=True, allow_no_improvement=True
        )
        assert outcome.exit_code == 0, outcome.lines

    def test_growing_past_the_ceiling_fails(self, fx: GitFixture) -> None:
        fx.write("sub/w.py", GOOD + "".join(f"A{i} = {i}\n" for i in range(370)))
        fx.snapshot("sub")
        base = fx.commit("base, under 400 lines")
        fx.write("sub/w.py", GOOD + "".join(f"A{i} = {i}\n" for i in range(400)))
        fx.snapshot("sub")
        fx.commit("grow past 400")
        outcome = fx.ratchet().check(
            fx.scorer(), base_ref=base, require_base=True, allow_no_improvement=True
        )
        assert outcome.exit_code == 1
        assert any("module_size" in line for line in outcome.lines)

    def test_new_function_module_passes(self, fx: GitFixture) -> None:
        fx.write("sub/w.py", GOOD)
        fx.snapshot("sub")
        base = fx.commit("base")
        fx.write("sub/api.py", FUNCTION_MODULE)
        fx.snapshot("sub")
        fx.commit("add api")
        outcome = fx.ratchet().check(fx.scorer(), base_ref=base, require_base=True)
        assert outcome.exit_code == 0, outcome.lines


class TestCeilingsAreWellFormed:
    def test_every_ceiling_is_a_le_metric_in_the_table(self) -> None:
        # max(value, target) ranks correctly only for a <= metric; a typo or a
        # >= metric here would silently change the ordering.
        for metric in Thresholds.CEILINGS:
            assert Thresholds.TABLE[metric][0] == "<="


class TestMissingBaseMetricFailsClosed:
    """A gated metric absent from a file's base row is judged by its target."""

    def test_missing_base_metric_over_target_regresses(self) -> None:
        review = FileReview(
            "sub/w.py",
            {"module_size": 5000.0, "avg_params": 1.0},
            {"avg_params": 2.0},
            {"module_size": 5000.0, "avg_params": 1.0},
            frozenset(),
        )
        assert "module_size" in review.regressed

    def test_missing_base_metric_within_target_is_no_improvement(self) -> None:
        review = FileReview(
            "sub/w.py",
            {"module_size": 50.0, "avg_params": 2.0},
            {"avg_params": 2.0},
            {"module_size": 50.0, "avg_params": 2.0},
            frozenset(),
        )
        assert not review.regressed
        assert not review.improved


class TestLegacyBaselineFields:
    """Adopter baselines written before PL-1685 still carry the removed metrics."""

    LEGACY: ClassVar[dict[str, float]] = {
        "method_ratio": 0.5,
        "class_to_func_ratio": 0.5,
        "classes_per_module": 1.0,
    }

    def test_check_passes_and_update_drops_fields_on_rewritten_rows(
        self, fx: GitFixture
    ) -> None:
        fx.write("sub/w.py", GOOD)
        fx.write("sub/other.py", GOOD)
        rows = Baseline.metrics_by_file(fx.scorer().results)
        fx.write_baseline({path: {**row, **self.LEGACY} for path, row in rows.items()})
        base = fx.commit("base with legacy fields")
        fx.write("sub/w.py", GROWN)
        updated = fx.writer().update(
            fx.scorer(),
            base_ref=base,
            require_base=True,
            allow_ci_write=True,
            source=None,
        )
        assert updated.exit_code == 0, updated.lines
        fx.commit("grow w.py")
        outcome = fx.ratchet().check(
            fx.scorer(), base_ref=base, require_base=True, allow_no_improvement=True
        )
        assert outcome.exit_code == 0, outcome.lines
        saved = json.loads((fx.root / ".oo-baseline.json").read_text())
        assert not set(self.LEGACY) & set(saved["sub/w.py"])
        assert set(self.LEGACY) <= set(saved["sub/other.py"])


class TestBranchComparesAgainstMergeBase:
    """A branch of several commits is judged against main, not against itself.

    PL-1685: rows regressed only against values an earlier commit on the same
    branch had recorded, while every row was equal or better against main.
    """

    def test_update_accepts_a_later_commit_still_better_than_main(
        self, fx: GitFixture
    ) -> None:
        fx.write("sub/w.py", WORSE)
        fx.snapshot("sub")
        main = fx.commit("main")
        fx.set_origin_main(main)
        fx.checkout_new("feature")
        fx.write("sub/w.py", GOOD)
        first = fx.writer().update(
            fx.scorer(),
            base_ref=main,
            require_base=True,
            allow_ci_write=True,
            source=None,
        )
        assert first.exit_code == 0, first.lines
        fx.commit("first: complexity 3 -> 1")
        fx.write("sub/w.py", MIDDLE)
        second = fx.writer().update(
            fx.scorer(),
            base_ref=main,
            require_base=True,
            allow_ci_write=True,
            source=None,
        )
        assert second.exit_code == 0, second.lines
        fx.commit("second: complexity 1 -> 2, still below main's 3")
        outcome = fx.ratchet().check(fx.scorer(), base_ref=main, require_base=True)
        assert outcome.exit_code == 0, outcome.lines

    def _relaxed_branch(self, fx: GitFixture) -> str:
        """Return main's sha after relaxing sub/w.py from GOOD to WORSE on a branch."""
        fx.write("sub/w.py", GOOD)
        fx.snapshot("sub")
        main = fx.commit("main")
        fx.set_origin_main(main)
        fx.checkout_new("feature")
        fx.write("sub/w.py", WORSE)
        relaxed = fx.writer().relax(
            fx.scorer(), "sub/w.py", justify="needed", allow_ci_write=True, source=None
        )
        assert relaxed.exit_code == 0, relaxed.lines
        fx.commit("relax w.py")
        return main

    def test_update_after_a_branch_relax_reruns_clean(self, fx: GitFixture) -> None:
        main = self._relaxed_branch(fx)
        rerun = fx.writer().update(
            fx.scorer(),
            base_ref=main,
            require_base=True,
            allow_ci_write=True,
            source=None,
        )
        assert rerun.exit_code == 0, rerun.lines

    def test_update_accepts_giving_back_part_of_a_relaxed_loss(
        self, fx: GitFixture
    ) -> None:
        main = self._relaxed_branch(fx)
        fx.write("sub/w.py", MIDDLE)  # complexity 3 -> 2, still worse than main's 1
        updated = fx.writer().update(
            fx.scorer(),
            base_ref=main,
            require_base=True,
            allow_ci_write=True,
            source=None,
        )
        assert updated.exit_code == 0, updated.lines
        fx.commit("partial improvement")
        outcome = fx.ratchet().check(
            fx.scorer(), base_ref=main, require_base=True, allow_no_improvement=True
        )
        assert outcome.exit_code == 0, outcome.lines

    def test_update_refuses_worsening_past_a_relaxed_value(
        self, fx: GitFixture
    ) -> None:
        main = self._relaxed_branch(fx)  # relaxed to WORSE, complexity 3
        fx.write(
            "sub/w.py",
            WORSE.replace("if self._n > 10:", "if self._n > 10 or self._n < -10:"),
        )
        updated = fx.writer().update(
            fx.scorer(),
            base_ref=main,
            require_base=True,
            allow_ci_write=True,
            source=None,
        )
        assert updated.exit_code == 1
        assert any("max_complexity" in line for line in updated.lines)

    def test_update_rerun_records_no_repeat_improvement(self, fx: GitFixture) -> None:
        fx.write("sub/w.py", WORSE)
        fx.snapshot("sub")
        main = fx.commit("main")
        fx.set_origin_main(main)
        fx.checkout_new("feature")
        fx.write("sub/w.py", GOOD)
        for _ in range(2):
            updated = fx.writer().update(
                fx.scorer(),
                base_ref=main,
                require_base=True,
                allow_ci_write=True,
                source=None,
            )
            assert updated.exit_code == 0, updated.lines
        audit = (fx.root / ".oo-audit.jsonl").read_text().splitlines()
        assert json.loads(audit[-2])["files_improved"] == 1
        assert json.loads(audit[-1])["files_improved"] == 0

    def test_relax_refuses_a_metric_with_no_recorded_value(
        self, fx: GitFixture
    ) -> None:
        fx.write("sub/w.py", GOOD)
        fx.snapshot("sub")
        row = json.loads((fx.root / ".oo-baseline.json").read_text())
        del row["sub/w.py"]["future_annotations"]
        fx.write_baseline(row)
        fx.commit("main, row missing future_annotations")
        fx.write("sub/w.py", GOOD.replace("from __future__ import annotations\n", ""))
        relaxed = fx.writer().relax(
            fx.scorer(), "sub/w.py", justify="x", allow_ci_write=True, source=None
        )
        assert relaxed.exit_code == 1, relaxed.lines

    def _improved_then_reverted(self, fx: GitFixture) -> tuple[str, dict[str, float]]:
        """Return main's sha and sub/w.py row; the branch improves then reverts."""
        fx.write("sub/w.py", WORSE)
        fx.snapshot("sub")
        main_row = json.loads((fx.root / ".oo-baseline.json").read_text())["sub/w.py"]
        main = fx.commit("main")
        fx.set_origin_main(main)
        fx.checkout_new("feature")
        fx.write("sub/w.py", GOOD)
        first = fx.writer().update(
            fx.scorer(),
            base_ref=main,
            require_base=True,
            allow_ci_write=True,
            source=None,
        )
        assert first.exit_code == 0, first.lines
        fx.commit("improve")
        fx.write("sub/w.py", WORSE)  # exactly main's contents again
        return main, main_row

    def test_update_restores_the_row_of_a_reverted_file(self, fx: GitFixture) -> None:
        main, main_row = self._improved_then_reverted(fx)
        updated = fx.writer().update(
            fx.scorer(),
            base_ref=main,
            require_base=True,
            allow_ci_write=True,
            source=None,
        )
        assert updated.exit_code == 0, updated.lines
        saved = json.loads((fx.root / ".oo-baseline.json").read_text())["sub/w.py"]
        assert saved["max_complexity"] == main_row["max_complexity"]

    def test_check_flags_a_stale_row_of_a_reverted_file(self, fx: GitFixture) -> None:
        main, _ = self._improved_then_reverted(fx)
        fx.commit("revert without updating the baseline")
        outcome = fx.ratchet().check(
            fx.scorer(), base_ref=main, require_base=True, allow_no_improvement=True
        )
        assert outcome.exit_code == 1
        assert any("baseline out of date" in line for line in outcome.lines)

    def test_a_new_file_is_not_counted_as_improved(self, fx: GitFixture) -> None:
        fx.write("sub/w.py", GOOD)
        fx.snapshot("sub")
        main = fx.commit("main")
        fx.set_origin_main(main)
        fx.checkout_new("feature")
        fx.write("sub/new.py", GOOD)
        fx.commit("add new.py")  # tracked, so it is in the diff, not a backfill
        updated = fx.writer().update(
            fx.scorer(),
            base_ref=main,
            require_base=True,
            allow_ci_write=True,
            source=None,
        )
        assert updated.exit_code == 0, updated.lines
        audit = (fx.root / ".oo-audit.jsonl").read_text().splitlines()
        assert json.loads(audit[-1])["files_improved"] == 0

    def test_update_still_refuses_a_regression_against_main(
        self, fx: GitFixture
    ) -> None:
        fx.write("sub/w.py", GOOD)
        fx.snapshot("sub")
        main = fx.commit("main")
        fx.set_origin_main(main)
        fx.checkout_new("feature")
        fx.write("sub/w.py", WORSE)
        outcome = fx.writer().update(
            fx.scorer(),
            base_ref=main,
            require_base=True,
            allow_ci_write=True,
            source=None,
        )
        assert outcome.exit_code == 1
        assert any("max_complexity" in line for line in outcome.lines)


@pytest.fixture
def fx(tmp_path: pytest.TempPathFactory) -> GitFixture:
    return GitFixture(tmp_path)  # type: ignore[arg-type]
