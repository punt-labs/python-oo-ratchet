"""This repository's own layers gate: the committed table and baseline agree."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from oo_ratchet.__main__ import main as dispatch

if TYPE_CHECKING:
    import pytest

ROOT = Path(__file__).resolve().parent.parent


class TestOwnLayers:
    """``layers --check`` over ``src/oo_ratchet`` passes the committed baseline."""

    def test_own_source_passes_the_committed_baseline(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(ROOT)
        code = dispatch(["layers", "src/oo_ratchet/", "--check"])
        out = capsys.readouterr().out
        assert (code, "PASS" in out) == (0, True), out
