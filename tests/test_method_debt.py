"""The design scan of this package reports none of the folded method debt."""

from __future__ import annotations

import contextlib
import inspect
import io
import json
from functools import cache
from pathlib import Path

import pytest

from oo_ratchet.__main__ import main as dispatch
from oo_ratchet.core.adapters.metricgate import MetricGate

SOURCE = Path(__file__).resolve().parent.parent / "src" / "oo_ratchet"


@cache
def own_findings() -> frozenset[tuple[str, str]]:
    """Return the (rule, symbol) pairs of the design scan over this package."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        dispatch(["design", str(SOURCE), "--json"])
    rows = json.loads(buffer.getvalue())["findings"]
    return frozenset((row["rule"], row["symbol"]) for row in rows)


@pytest.mark.parametrize(
    ("rule", "symbol"),
    [
        ("size-cap", "MetricGate.bless"),
        ("feature-envy", "Check._verdict"),
        ("feature-envy", "Reconcile._plan"),
        ("feature-envy", "RebaselineFiles._classify"),
        ("feature-envy", "PlanApplier._record"),
        ("feature-envy", "PlanApplier._write"),
        ("feature-envy", "TotalReview.of"),
    ],
)
def test_method_debt_is_not_reported(rule: str, symbol: str) -> None:
    assert (rule, symbol) not in own_findings()


def test_metric_gate_bless_takes_one_request() -> None:
    params = list(inspect.signature(MetricGate.bless).parameters)
    assert params == ["self", "request"]
