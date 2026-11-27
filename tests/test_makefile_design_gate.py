"""The Makefile and CI run the package's own design gate on itself."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _make_dry_run(*args: str) -> str:
    result = subprocess.run(
        ["make", "-n", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


class TestCheckDesignTarget:
    def test_target_runs_enforced_shadow_check_with_the_given_base(self) -> None:
        out = _make_dry_run("check-design", "DESIGN_BASE=--shadow-check abc123")
        assert "oo-ratchet design src/oo_ratchet/" in out
        assert "--shadow-check abc123" in out
        assert "--enforce" in out

    def test_check_runs_the_design_gate(self) -> None:
        out = _make_dry_run("check", "DESIGN_BASE=--shadow-check abc123")
        assert "oo-ratchet design" in out

    def test_ci_runs_the_design_gate_on_pull_requests_and_main(self) -> None:
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        assert ci.count("make check-design") == 2
