"""Seeded design recall, precision, ordering and behavior contracts."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import TypedDict, cast

import pytest

from oo_ratchet.design.findings import Rules
from oo_ratchet.design.scanner import DesignScanner

type Key = tuple[str, str, str]


class ExpectedFinding(TypedDict):
    rule: str
    path: str
    symbol: str


class Variant(TypedDict):
    findings: list[ExpectedFinding]


class Expectations(TypedDict):
    bad: Variant
    good: Variant


ROOT = Path(__file__).resolve().parents[1] / "evals" / "design"
PAIRS = sorted(path.parent for path in ROOT.glob("*/expected.toml"))
VARIANTS = ("bad", "good")
KNOWN_MISFIRES: dict[tuple[str, str], Key] = {
    ("decoys", "bad"): (Rules.STATELESS_SINGLE, "adapters/wire.py", "Codec"),
    ("decoys", "good"): (Rules.STATELESS_SINGLE, "adapters/wire.py", "Codec"),
    ("layer-leak", "good"): (Rules.CONCRETE_IMPORT, "entry.py", "FeeStore"),
}


def _expected(pair: Path, variant: str) -> set[Key]:
    doc = cast("Expectations", tomllib.loads((pair / "expected.toml").read_text()))
    rows = doc["bad"] if variant == "bad" else doc["good"]
    return {(row["rule"], row["path"], row["symbol"]) for row in rows["findings"]}


def _scan(root: Path) -> set[Key]:
    layers = root.parents[1] / "layers.toml"
    # Scan a copy outside the checkout: the repository's own pyproject layer
    # table must not reach the fixtures through the ancestor lookup.
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / root.name
        shutil.copytree(root, copy)
        doc = json.loads(
            DesignScanner(copy, layers if layers.is_file() else None).report.to_json()
        )
    assert doc["skipped"] == []
    return {
        (row["rule"], Path(row["path"]).relative_to(copy).as_posix(), row["symbol"])
        for row in doc["findings"]
    }


@pytest.fixture(scope="module")
def findings() -> dict[tuple[Path, str], set[Key]]:
    return {
        (pair, variant): _scan(pair / variant / "loans")
        for pair in PAIRS
        for variant in VARIANTS
    }


def test_eval_catalogue() -> None:
    assert {p.name for p in PAIRS} == {
        "anemic",
        "data-clump",
        "misplaced-fn",
        "primitive",
        "tag-switch",
        "middle-man",
        "split-cohesion",
        "layer-leak",
        "over-split",
        "god-class",
        "decoys",
    }
    for pair in PAIRS:
        for variant in VARIANTS:
            expected = _expected(pair, variant)
            assert all(key[0] in Rules.ordered() for key in expected)
            assert all(
                (pair / variant / "loans" / key[1]).is_file() for key in expected
            )


@pytest.mark.parametrize("pair", PAIRS, ids=lambda p: p.name)
@pytest.mark.parametrize("variant", VARIANTS)
def test_implemented_recall(
    pair: Path, variant: str, findings: dict[tuple[Path, str], set[Key]]
) -> None:
    expected = {key for key in _expected(pair, variant) if key[0] in Rules.ordered()}
    assert expected <= findings[pair, variant]


@pytest.mark.parametrize("pair", PAIRS, ids=lambda p: p.name)
@pytest.mark.parametrize("variant", VARIANTS)
def test_implemented_precision(
    pair: Path, variant: str, findings: dict[tuple[Path, str], set[Key]]
) -> None:
    actual = {key for key in findings[pair, variant] if key[0] in Rules.ordered()}
    known = KNOWN_MISFIRES.get((pair.name, variant))
    if known is not None:
        actual.discard(known)
    assert actual <= _expected(pair, variant)


@pytest.mark.parametrize(
    ("pair_name", "variant", "key"),
    [
        pytest.param(
            pair_name,
            variant,
            key,
            id=f"{pair_name}-{variant}-{key[2]}",
            marks=pytest.mark.xfail(
                strict=True,
                reason=(
                    "Advisory rules lack layer/codec exemptions: intentional "
                    "from_wire codec or entry composition-root import"
                ),
            ),
        )
        for (pair_name, variant), key in KNOWN_MISFIRES.items()
    ],
)
def test_known_precision_misfire(
    pair_name: str,
    variant: str,
    key: Key,
    findings: dict[tuple[Path, str], set[Key]],
) -> None:
    assert key not in findings[ROOT / pair_name, variant]


@pytest.mark.parametrize(
    "pair",
    [
        pytest.param(p, id=p.name)
        for p in PAIRS
        if any(k[0] in Rules.ordered() for k in _expected(p, "bad"))
    ],
)
def test_implemented_ordering(
    pair: Path, findings: dict[tuple[Path, str], set[Key]]
) -> None:
    bad = {key for key in findings[pair, "bad"] if key[0] in Rules.ordered()}
    good = {key for key in findings[pair, "good"] if key[0] in Rules.ordered()}
    for variant, keys in (("bad", bad), ("good", good)):
        known = KNOWN_MISFIRES.get((pair.name, variant))
        if known is not None:
            keys.discard(known)
    assert len(bad) > len(good)


@pytest.mark.parametrize("pair", PAIRS, ids=lambda p: p.name)
@pytest.mark.parametrize("variant", VARIANTS)
def test_behavior(pair: Path, variant: str) -> None:
    result = subprocess.run(
        [sys.executable, str(pair / "behavior.py"), str(pair / variant)],
        cwd=pair,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("pair", PAIRS, ids=lambda p: p.name)
@pytest.mark.parametrize("variant", VARIANTS)
def test_repeat_scan_yields_same_keys(
    pair: Path, variant: str, findings: dict[tuple[Path, str], set[Key]]
) -> None:
    assert _scan(pair / variant / "loans") == findings[pair, variant]


def test_module_rename_preserves_symbol_keys(tmp_path: Path) -> None:
    """A move changes only the path component, never rule/symbol identity."""
    source = ROOT / "over-split" / "bad" / "loans"
    copied = shutil.copytree(source, tmp_path / "loans")
    (copied / "validate.py").rename(copied / "validation.py")
    api = copied / "api.py"
    api.write_text(
        api.read_text().replace("from .validate import", "from .validation import")
    )
    normalized = {
        (rule, "validate.py" if path == "validation.py" else path, symbol)
        for rule, path, symbol in _scan(copied)
    }
    assert normalized == _scan(source)
