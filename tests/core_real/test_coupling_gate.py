"""The coupling gate on the shared core behaves as the existing gate does.

Every scenario in ``coupling_scenarios`` is played twice against identical real
git repositories: once through the existing gate's CLI entry point and once
through the CLI that runs on the shared core. The transcripts (exit codes,
report lines, baseline text, audit lines) must be equal.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from oo_ratchet.coupling.corecli import main as new_main

from oo_ratchet.coupling.cli import main as old_main
from tests.core_real.coupling_play import Play
from tests.core_real.coupling_scenarios import SCENARIOS

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_core_gate_matches_existing_gate(
    name: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = Play(tmp_path / "old", old_main, capsys, monkeypatch)
    SCENARIOS[name](old)
    new = Play(tmp_path / "new", new_main, capsys, monkeypatch)
    SCENARIOS[name](new)
    assert old.steps, "a scenario must record at least one run"
    assert new.steps == old.steps
