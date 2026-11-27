"""The design scan of this package reports none of the folded hollow classes."""

from __future__ import annotations

import contextlib
import io
import json
from functools import cache
from pathlib import Path

import pytest

from oo_ratchet.__main__ import main as dispatch
from oo_ratchet.core.domain.findings import Rules
from oo_ratchet.core.domain.layer_config import LayerConfig
from oo_ratchet.core.domain.layer_table import LayerTable

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
        (Rules.STATELESS_BAG, "LayerTable"),
        (Rules.STATELESS_SINGLE, "Rules"),
        (Rules.STATELESS_SINGLE, "TypeReference"),
        (Rules.STATELESS_SINGLE, "NulListing"),
        (Rules.STATELESS_SINGLE, "_ExitStatus"),
        (Rules.MIDDLE_MAN, "BaseTree"),
        (Rules.MIDDLE_MAN, "PackageLayout"),
        (Rules.SPLIT_COHESION, "DataInventory"),
        (Rules.SPLIT_COHESION, "StrictViolations"),
    ],
)
def test_hollow_class_is_not_reported(rule: str, symbol: str) -> None:
    assert (rule, symbol) not in own_findings()


def test_rules_are_an_enum_that_describe_themselves() -> None:
    assert Rules.STATELESS_SINGLE.description.startswith("stateless class")
    assert Rules.ordered()[0] == "stateless-single-method"
    assert len(Rules.ordered()) == len(list(Rules))


def test_layer_table_holds_the_table_it_reads() -> None:
    text = '[tool.oo-ratchet.layers]\ndomain = ["pkg.*"]\n'
    config = LayerTable.from_text(text, "t").config()
    assert isinstance(config, LayerConfig)
    assert config.layer("pkg.a") == "domain"
    assert LayerTable.from_text("", "t").config() is None


def test_layer_table_reads_the_nearest_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.oo-ratchet.layers]\ndomain = ["pkg.*"]\n', encoding="utf-8"
    )
    inner = tmp_path / "src"
    inner.mkdir()
    config = LayerTable.read(inner).config()
    assert config is not None
    assert config.layer("pkg.b") == "domain"
    assert LayerTable.read(tmp_path / "empty").config() is not None
