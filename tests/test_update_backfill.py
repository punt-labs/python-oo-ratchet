"""Scoped updates backfill missing rows without refreshing untouched debt."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest

from oo_ratchet.coupling.cli import main as coupling_main
from oo_ratchet.oo.cli import main as oo_main

if TYPE_CHECKING:
    from tests.conftest import GitSandbox

pytestmark = pytest.mark.slow

SOURCE = "class Thing:\n    def name(self) -> str:\n        return 'thing'\n"


@pytest.mark.parametrize(
    ("run", "baseline"),
    [(coupling_main, ".oo-coupling-baseline.json"), (oo_main, ".oo-baseline.json")],
)
@pytest.mark.parametrize("scenario", ["post_merge", "branch", "untracked"])
def test_update_backfills_missing_rows(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    run: Callable[[list[str]], int],
    baseline: str,
    scenario: str,
) -> None:
    monkeypatch.chdir(git_sandbox.root)
    for name in ("a", "b", "untouched"):
        git_sandbox.write(f"pkg/{name}.py", SOURCE)
    assert run(["pkg", "--rebaseline", "--allow-ci-write"]) == 0
    path = git_sandbox.root / baseline
    entries = json.loads(path.read_text())
    del entries["pkg/b.py"]
    entries["pkg/untouched.py"] = {"deliberately_stale": 42.0}
    path.write_text(json.dumps(entries))
    if scenario == "untracked":
        (git_sandbox.root / "pkg/b.py").unlink()
    base = git_sandbox.commit("base with missing row")
    git_sandbox.run_git("update-ref", "refs/remotes/origin/main", base)
    if scenario == "branch":
        git_sandbox.run_git("checkout", "-b", "feature")
        git_sandbox.write("pkg/a.py", SOURCE + "\n# touched\n")
        git_sandbox.commit("touch a only")
        git_sandbox.write("pkg/new.py", SOURCE)
        git_sandbox.run_git("add", "pkg/new.py")
    elif scenario == "untracked":
        git_sandbox.write("pkg/b.py", SOURCE)
    else:
        assert git_sandbox.run_git("diff", "--name-only", base) == ""
    capsys.readouterr()
    assert run(["pkg", "--update", "--allow-ci-write"]) == 0
    result = json.loads(path.read_text())
    assert "pkg/b.py" in result
    if scenario == "branch":
        assert "pkg/new.py" in result
    assert result["pkg/untouched.py"] == entries["pkg/untouched.py"]
    assert result["pkg/a.py"] == entries["pkg/a.py"]
    output = capsys.readouterr().out
    assert "  backfilled: pkg/b.py" in output
    assert "  backfilled: pkg/new.py" not in output
    audit_path = git_sandbox.root / baseline.replace("baseline.json", "audit.jsonl")
    audit = json.loads(audit_path.read_text().splitlines()[-1])
    assert audit["backfilled"] == ["pkg/b.py"]
    assert "pkg/b.py" not in audit["deltas"]
    # The branch adds pkg/new.py. Coupling counts a new row as improved;
    # OO counts only files whose metrics beat a prior row (PL-1685).
    expected_improved = 1 if scenario == "branch" and run is coupling_main else 0
    assert audit["files_improved"] == expected_improved
    assert f"files improved: {expected_improved}" in output
    if scenario == "branch":
        assert "pkg/new.py" in audit["deltas"]
        assert all(old == 0.0 for old, _ in audit["deltas"]["pkg/new.py"].values())


@pytest.mark.parametrize("run", [coupling_main, oo_main])
@pytest.mark.parametrize("scenario", ["bootstrap", "failure", "rename"])
def test_update_backfill_reporting_exclusions(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    run: Callable[[list[str]], int],
    scenario: str,
) -> None:
    monkeypatch.chdir(git_sandbox.root)
    git_sandbox.write("pkg/a.py", SOURCE)
    if scenario != "bootstrap":
        assert run(["pkg", "--rebaseline", "--allow-ci-write"]) == 0
    git_sandbox.write("pkg/b.py", SOURCE)
    base = git_sandbox.commit("base")
    if scenario != "bootstrap":
        git_sandbox.run_git("update-ref", "refs/remotes/origin/main", base)
    if scenario == "failure":
        git_sandbox.write("pkg/a.py", "def broken(\n")
    elif scenario == "rename":
        git_sandbox.run_git("mv", "pkg/a.py", "pkg/renamed.py")
    capsys.readouterr()
    assert run(["pkg", "--update", "--allow-ci-write"]) == (
        1 if scenario == "failure" else 0
    )
    output = capsys.readouterr().out
    if scenario == "rename":
        assert "  backfilled: pkg/b.py" in output
        assert "  backfilled: pkg/renamed.py" not in output
    else:
        assert "backfilled:" not in output
    baseline = (
        ".oo-coupling-baseline.json" if run is coupling_main else ".oo-baseline.json"
    )
    audit_path = git_sandbox.root / baseline.replace("baseline.json", "audit.jsonl")
    audit = json.loads(audit_path.read_text().splitlines()[-1])
    if scenario == "bootstrap":
        assert "backfilled" not in audit
    else:
        assert audit["backfilled"] == ["pkg/b.py"]
        assert "pkg/b.py" not in audit["deltas"]
