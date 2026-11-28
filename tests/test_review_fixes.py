"""Regressions from PR #1 review: push tripwire on every gate, scoped updates."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from oo_ratchet.coupling.cli import main as coupling_main
from oo_ratchet.oo.cli import main as oo_main
from oo_ratchet.suppression.cli import main as suppression_main

if TYPE_CHECKING:
    from tests.conftest import GitSandbox

_SRC = (
    "from __future__ import annotations\n\n\n"
    "class Thing:\n"
    "    def __new__(cls) -> Thing:\n"
    "        return super().__new__(cls)\n\n"
    "    def name(self) -> str:\n"
    '        return "thing"\n'
)


def _adopt(sandbox: GitSandbox) -> str:
    """Commit a tree with no source, then the adoption commit with source + baselines.

    Points ``origin/main`` at the adoption tip and returns the pre-adoption sha.
    """
    sandbox.write("README.md", "pre-adoption\n")
    pre = sandbox.commit("pre-adoption")
    sandbox.write("src/pkg/__init__.py", "")
    sandbox.write("src/pkg/thing.py", _SRC)
    assert oo_main(["src/pkg", "--rebaseline", "--allow-ci-write"]) == 0
    assert suppression_main(["src/pkg", "--update", "--allow-ci-write"]) == 0
    adoption = sandbox.commit("adoption")
    sandbox.run_git("update-ref", "refs/remotes/origin/main", adoption)
    return pre


@pytest.mark.parametrize(
    ("gate", "extra"),
    [
        (oo_main, ["--allow-no-improvement"]),
        (suppression_main, []),
    ],
)
def test_push_tripwire_passes_only_the_adoption_merge(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    gate: object,
    extra: list[str],
) -> None:
    monkeypatch.chdir(git_sandbox.root)
    pre = _adopt(git_sandbox)
    run = gate if callable(gate) else None
    assert run is not None
    args = ["src/pkg", "--check", "--base-ref", pre, "--require-base", *extra]
    assert run(args) == 1
    assert run([*args, "--tripwire"]) == 0


@pytest.mark.parametrize(
    ("gate", "baseline"),
    [
        (oo_main, ".oo-baseline.json"),
        (coupling_main, ".oo-coupling-baseline.json"),
    ],
)
def test_scoped_update_keeps_rows_of_other_modified_files(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    gate: object,
    baseline: str,
) -> None:
    monkeypatch.chdir(git_sandbox.root)
    run = gate if callable(gate) else None
    assert run is not None
    git_sandbox.write("src/pkg/__init__.py", "")
    git_sandbox.write("src/pkg/a.py", _SRC)
    git_sandbox.write("src/pkg/b.py", _SRC)
    assert run(["src/pkg", "--rebaseline", "--allow-ci-write"]) == 0
    base = git_sandbox.commit("base")
    git_sandbox.write("src/pkg/a.py", _SRC + "# edited\n")
    git_sandbox.write("src/pkg/b.py", _SRC + "# edited\n")
    args = ["src/pkg/a.py", "--update", "--base-ref", base, "--allow-ci-write"]
    run(args)
    assert "src/pkg/b.py" in (Path(git_sandbox.root) / baseline).read_text()
