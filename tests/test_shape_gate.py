"""PL-1685: the OO gate does not push code into small, single-class modules.

The gate used to compare ``module_size`` and ``classes_per_module`` file by
file and fail on any growth, and required ``method_ratio`` and
``class_to_func_ratio`` floors. Together they rewarded splitting cohesive
code into tiny one-class modules and wrapping functions in stateless classes.
Module size is now an absolute ceiling only, and the class-count and ratio
metrics are not gated.
"""

from __future__ import annotations

import pytest

from oo_ratchet.oo.thresholds import Thresholds
from tests.test_oo_ratchet import GOOD, GitFixture

pytestmark = pytest.mark.slow

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

    def test_new_function_module_passes(self, fx: GitFixture) -> None:
        fx.write("sub/w.py", GOOD)
        fx.snapshot("sub")
        base = fx.commit("base")
        fx.write("sub/api.py", FUNCTION_MODULE)
        fx.snapshot("sub")
        fx.commit("add api")
        outcome = fx.ratchet().check(fx.scorer(), base_ref=base, require_base=True)
        assert outcome.exit_code == 0, outcome.lines


@pytest.fixture
def fx(tmp_path: pytest.TempPathFactory) -> GitFixture:
    return GitFixture(tmp_path)  # type: ignore[arg-type]
