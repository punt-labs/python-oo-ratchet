"""The design scan of this package reports none of the folded hollow classes."""

from __future__ import annotations

import ast
import contextlib
import io
import json
from functools import cache
from pathlib import Path

import pytest

from oo_ratchet.__main__ import main as dispatch
from oo_ratchet.core.adapters.layertablefile import LayerTableFile
from oo_ratchet.core.domain.findings import Rules
from oo_ratchet.core.domain.layer_config import LayerConfig
from oo_ratchet.core.domain.layer_table import LayerTable
from oo_ratchet.core.domain.modules import Module

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
        (Rules.ENVIED_DATA, "Module"),
        (Rules.SPLIT_COHESION, "Module"),
        (Rules.SPLIT_COHESION, "LayerConfig"),
        (Rules.FEATURE_ENVY, "SizeRules._module"),
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
    config = LayerTableFile.read(inner).table.config()
    assert config is not None
    assert config.layer("pkg.b") == "domain"
    assert LayerTableFile.read(tmp_path / "empty").table.config() is not None


def _module(key: str, source: str, name: str = "a.py") -> Module:
    path = Path("pkg") / name
    return Module(key, path, ast.parse(source), {}, key)


def test_module_builds_its_own_finding() -> None:
    found = _module("a", "x = 1\n").finding(Rules.SIZE_CAP, 3, "sym", "why")
    assert (found.rule, found.path, found.line, found.symbol, found.detail) == (
        "size-cap",
        str(Path("pkg") / "a.py"),
        3,
        "sym",
        "why",
    )


def test_module_lists_its_from_imports() -> None:
    source = "import os\nfrom . import b\nif True:\n    from c import d\n"
    froms = _module("a", source).import_froms()
    assert [node.lineno for node in froms] == [2, 4]


@pytest.mark.parametrize(
    ("key", "name", "parts"),
    [
        ("__init__", "__init__.py", []),
        ("a", "__init__.py", ["a"]),
        ("a.b", "b.py", ["a"]),
        ("c", "c.py", []),
    ],
)
def test_module_names_the_package_it_sits_in(
    key: str, name: str, parts: list[str]
) -> None:
    assert _module(key, "", name).package_parts() == parts


def test_module_finds_the_import_that_exports_a_name() -> None:
    source = "from .core import Engine as Public\nfrom .x import Y\n"
    module = _module("pkg", source, "__init__.py")
    found = module.reexport("Public")
    assert found is not None
    assert (found[0].lineno, found[1]) == (1, "Engine")
    assert module.reexport("Missing") is None
