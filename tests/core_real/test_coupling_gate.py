"""The coupling gate on the shared core behaves as the gate it replaced did.

Every scenario in ``coupling_scenarios`` is played against a real git
repository through the gate's CLI entry point. The transcript (exit codes,
report lines, baseline text, audit lines) must equal the one in
``golden_coupling_gate.json``.

The golden file was recorded by playing the same scenarios through the
coupling CLI as it was before it moved onto the core. During the move both
implementations ran side by side and every transcript was equal, except the
wording of a state error (``run_state_error`` steps), which the core words
once for every gate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from oo_ratchet.coupling.cli import main
from tests.core_real.coupling_play import Play
from tests.core_real.coupling_scenarios import SCENARIOS

pytestmark = pytest.mark.slow

GOLDEN: dict[str, list[dict[str, Any]]] = json.loads(
    (Path(__file__).parent / "golden_coupling_gate.json").read_text()
)


def test_every_scenario_has_a_recorded_transcript() -> None:
    assert sorted(GOLDEN) == sorted(SCENARIOS)


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_gate_transcript_matches_the_recorded_one(
    name: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    play = Play(tmp_path, main, capsys, monkeypatch)
    SCENARIOS[name](play)
    assert play.steps, "a scenario must record at least one run"
    assert json.loads(json.dumps(play.steps)) == GOLDEN[name]
