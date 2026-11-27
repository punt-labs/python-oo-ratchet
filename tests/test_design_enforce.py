"""``design --shadow-check --enforce`` blocks only on gate-capable rules (B4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from oo_ratchet.__main__ import main
from oo_ratchet.core.domain.findings import Rules
from tests.test_design_shadow import repo as repo
from tests.test_design_shadow import seed, write

WRAPPED = (
    "class Slug:\n    @staticmethod\n    def of(text: str) -> str:\n"
    "        return text\n"
)
LONG = "x = 0\n" * 401
PRIMITIVE = "def pair(a: int, b: int) -> int:\n    return a + b\n"
ARGS = ("--shadow-check", "base")


def run(repo: Path, *flags: str) -> int:
    return main(["design", str(repo / "pkg"), *ARGS, *flags])


@pytest.mark.parametrize(
    ("after", "rule"),
    [(WRAPPED, Rules.STATELESS_SINGLE), (LONG, Rules.SIZE_CAP)],
)
def test_enforce_exits_one_on_an_added_gate_capable_key(
    repo: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    after: str,
    rule: str,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    seed(repo, {"model.py": "def _f(): return 1\n"})
    write(repo, {"model.py": after})
    assert run(repo, "--enforce") == 1
    captured = capsys.readouterr()
    assert f"({rule}, pkg.model" in captured.err
    assert captured.err.startswith("oo-ratchet design: --enforce")
    assert "would-fail" in captured.out


def test_without_enforce_the_same_key_still_exits_zero(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(repo, {"model.py": "def _f(): return 1\n"})
    write(repo, {"model.py": WRAPPED})
    assert run(repo) == 0
    assert not capsys.readouterr().err


def test_enforce_ignores_added_keys_of_advisory_rules(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(repo, {"model.py": "def _f(): return 1\n"})
    write(repo, {"model.py": PRIMITIVE})
    assert run(repo, "--enforce") == 0
    output = capsys.readouterr()
    assert "would-fail: tier1" in output.out
    assert not output.err


def test_enforce_passes_when_nothing_is_added(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(repo, {"model.py": WRAPPED})
    assert run(repo, "--enforce") == 0
    assert not capsys.readouterr().err


def test_enforce_needs_shadow_check(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(repo, {"model.py": WRAPPED})
    assert main(["design", str(repo / "pkg"), "--enforce"]) == 2
    output = capsys.readouterr()
    assert not output.out
    assert "--enforce needs --shadow-check" in output.err


def test_gate_capable_rules_are_documented_design_rules() -> None:
    assert set(Rules.ordered()) >= Rules.GATE_CAPABLE
    assert {
        Rules.LAYER_IMPORT,
        Rules.SIZE_CAP,
        Rules.THICK_ENTRY,
        Rules.UNLAYERED_MODULE,
        Rules.STATELESS_SINGLE,
    } == Rules.GATE_CAPABLE
