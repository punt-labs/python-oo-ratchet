"""The gated metrics are Metric objects held by a MetricSet, not function bags."""

from __future__ import annotations

import importlib

import pytest

from oo_ratchet.core.domain.metrics import MetricSet
from oo_ratchet.coupling.thresholds import COUPLING_METRICS, CouplingTargets
from oo_ratchet.oo.thresholds import OO_METRICS


class TestFunctionBagsAreGone:
    """``Thresholds`` and ``CouplingThresholds`` no longer exist."""

    @pytest.mark.parametrize(
        ("module", "name"),
        [
            ("oo_ratchet.oo.thresholds", "Thresholds"),
            ("oo_ratchet.coupling.thresholds", "CouplingThresholds"),
        ],
    )
    def test_class_removed(self, module: str, name: str) -> None:
        assert not hasattr(importlib.import_module(module), name)


class TestOoMetrics:
    """The OO table as one Metric per name."""

    def test_names_in_table_order(self) -> None:
        assert OO_METRICS.names == (
            "encapsulation_ratio",
            "avg_params",
            "max_complexity",
            "avg_complexity",
            "module_size",
            "init_violations",
            "public_attr_violations",
            "future_annotations",
        )

    def test_ceilings_are_the_two_means_and_size(self) -> None:
        assert set(OO_METRICS.ceilings) == {
            "module_size",
            "avg_params",
            "avg_complexity",
        }

    def test_each_metric_knows_its_direction(self) -> None:
        metric = OO_METRICS.metric("encapsulation_ratio")
        assert (metric.op, metric.target, metric.ceiling) == (">=", 1.0, False)
        assert OO_METRICS.metric("module_size").ceiling is True

    def test_describe_labels_match_the_json_report(self) -> None:
        assert OO_METRICS.metric("max_complexity").describe() == "<= 10"


class TestCouplingTargets:
    """Per-file targets come from the object, not from a table lookup."""

    def test_strict_target(self) -> None:
        targets = CouplingTargets()
        assert targets.metric("efferent_coupling", "src/p/core.py").meets(10)
        assert not targets.metric("efferent_coupling", "src/p/core.py").meets(11)

    def test_main_is_relaxed(self) -> None:
        assert CouplingTargets().metric("public_names", "src/p/__main__.py").meets(90)

    def test_cap_widens_equality_to_a_ceiling(self) -> None:
        targets = CouplingTargets({"p/hub.py": {"circular_imports": 1.0}})
        assert targets.metric("circular_imports", "p/hub.py").meets(1)
        assert not targets.metric("circular_imports", "p/hub.py").meets(2)

    def test_set_is_a_metric_set(self) -> None:
        assert isinstance(COUPLING_METRICS, MetricSet)
