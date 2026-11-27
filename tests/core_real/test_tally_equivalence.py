"""The suppression gate on the shared core matches the existing gate on real repos.

Each scenario builds a real git repository, runs the existing gate through
``oo_ratchet.suppression.cli.main``, restores the gate's state files, then runs
the core path (``core_main``) over the same repository. Exit code, stdout and
every state file (baseline, audit log, ceiling ledger, timestamps masked) must
be identical.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from oo_ratchet.suppression.cli import core_main, main
from tests.conftest import GitSandbox

pytestmark = pytest.mark.slow

STATE = (
    ".suppression-baseline.json",
    ".suppression-audit.jsonl",
    ".suppression-relax.json",
)
STAMP = re.compile(r'("(?:updated_at|ts|added_at)": ?)"[^"]*"')
ONE = "x = 1  # noqa\n"
TWO = "x = 1  # noqa\ny = 2  # noqa\n"
THREE = "x = 1  # noqa\ny = 2  # noqa\nz = 3  # noqa\n"
CLEAN = "x = 1\n"


class Twin:
    """Run one argv through both gates on the same repository state."""

    def __init__(self, box: GitSandbox, capsys: pytest.CaptureFixture[str]) -> None:
        self.box = box
        self.capsys = capsys

    def source(self, text: str) -> None:
        self.box.write("pkg/a.py", text)

    def files(self) -> dict[str, str | None]:
        out: dict[str, str | None] = {}
        for name in STATE:
            path = self.box.root / name
            out[name] = STAMP.sub(r'\1"T"', path.read_text()) if path.exists() else None
        return out

    def restore(self, saved: dict[str, str | None]) -> None:
        for name, text in saved.items():
            path = self.box.root / name
            if text is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(text)

    def run(self, *argv: str) -> tuple[int, str]:
        """Return (code, stdout) after asserting both gates agree."""
        saved = {
            n: (self.box.root / n).read_text() if (self.box.root / n).exists() else None
            for n in STATE
        }
        self.capsys.readouterr()
        old_code = main(list(argv))
        old = (old_code, self.capsys.readouterr().out, self.files())
        self.restore(saved)
        new_code = core_main(list(argv))
        new = (new_code, self.capsys.readouterr().out, self.files())
        assert new == old
        return old_code, old[1]


@pytest.fixture
def twin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Twin:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)  # CI refuses baseline writes
    return Twin(GitSandbox(tmp_path), capsys)


def check(base: str, *flags: str) -> list[str]:
    return ["pkg", "--check", "--base-ref", base, *flags]


def test_regression_is_caught(twin: Twin) -> None:
    twin.source(ONE)
    base = twin.box.commit("base")
    twin.source(TWO)
    code, out = twin.run(*check(base, "--require-base"))
    assert code == 1
    assert "pkg/a.py: +1 unwaived (1 -> 2)" in out


def test_unchanged_passes(twin: Twin) -> None:
    twin.source(ONE)
    base = twin.box.commit("base")
    code, out = twin.run(*check(base, "--require-base"))
    assert (code, "PASS: suppression count unchanged" in out) == (0, True)


def test_reduction_is_credited(twin: Twin) -> None:
    twin.source(TWO)
    base = twin.box.commit("base")
    twin.source(ONE)
    code, out = twin.run(*check(base, "--require-base"))
    assert (code, "decreased by 1" in out) == (0, True)


def test_base_is_rescanned_not_read_from_a_stale_baseline(twin: Twin) -> None:
    twin.source(CLEAN)
    assert twin.run("pkg", "--update")[0] == 0
    twin.box.commit("baseline at zero")
    twin.source(ONE)
    base = twin.box.commit("suppression lands, baseline not refreshed")
    code, out = twin.run(*check(base, "--require-base"))
    assert (code, "unchanged" in out) == (0, True)


def test_relax_writes_a_ceiling_the_check_honours(twin: Twin) -> None:
    twin.source(ONE)
    base = twin.box.commit("base")
    twin.source(TWO)
    path = "pkg/a.py"
    code, out = twin.run(
        "pkg", "--relax", path, "--justify", "needed", "--base-ref", base
    )
    assert (code, "Relaxed" in out) == (0, True)
    code, out = twin.run(*check(base, "--require-base"))
    assert (code, "1 waived" in out) == (0, True)


def test_ceiling_does_not_cover_a_larger_rise(twin: Twin) -> None:
    twin.source(ONE)
    base = twin.box.commit("base")
    twin.source(TWO)
    path = "pkg/a.py"
    twin.run("pkg", "--relax", path, "--justify", "needed", "--base-ref", base)
    twin.source(THREE)
    code, out = twin.run(*check(base, "--require-base"))
    assert (code, "+1 unwaived" in out) == (1, True)


def test_merged_ceiling_is_retired(twin: Twin) -> None:
    twin.source(ONE)
    pre = twin.box.commit("base")
    twin.source(THREE)
    path = "pkg/a.py"
    twin.run("pkg", "--relax", path, "--justify", "needed", "--base-ref", pre)
    twin.box.commit("merge the relaxed change")
    twin.source(CLEAN)
    cleanup = twin.box.commit("cleanup")
    twin.source(TWO)
    code, out = twin.run(*check(cleanup, "--require-base"))
    assert (code, "+2 unwaived" in out) == (1, True)


def test_relax_refusals(twin: Twin) -> None:
    twin.source(ONE)
    base = twin.box.commit("base")
    path = "pkg/a.py"
    flags = ("--base-ref", base)
    assert twin.run("pkg", "--relax", path, "--justify", " ", *flags)[0] == 1
    assert twin.run("pkg", "--relax", path, "--justify", "why", *flags)[0] == 1
    twin.source(TWO)
    assert (
        twin.run("pkg", "--relax", path, "--justify", "why", "--base-ref", "0" * 40)[0]
        == 1
    )


def test_adoption_without_a_base_source_tree(twin: Twin) -> None:
    twin.box.write("README.md", "placeholder\n")
    base = twin.box.commit("before pkg existed")
    twin.source(ONE)
    code, out = twin.run(*check(base))
    assert (code, "bootstrap pass" in out) == (0, True)
    twin.run("pkg", "--update")
    twin.box.commit("adopt")
    assert twin.run(*check(base))[0] == 1  # in-tree baseline, no origin/main
    assert twin.run(*check(base, "--tripwire"))[0] == 0


def test_tip_already_carrying_the_tree_demands_a_rebase(twin: Twin) -> None:
    twin.box.write("README.md", "placeholder\n")
    base = twin.box.commit("before pkg existed")
    twin.source(ONE)
    tip = twin.box.commit("pkg lands")
    twin.box.run_git("update-ref", "refs/remotes/origin/main", tip)
    code, out = twin.run(*check(base))
    assert (code, "rebase onto current main" in out) == (1, True)


def test_tripwire_without_a_baseline_fails(twin: Twin) -> None:
    twin.box.write("README.md", "placeholder\n")
    base = twin.box.commit("before pkg existed")
    twin.source(ONE)
    assert twin.run(*check(base, "--tripwire"))[0] == 1


def test_no_base(twin: Twin) -> None:
    twin.source(ONE)
    twin.box.commit("first")
    bad = "0" * 40
    assert twin.run(*check(bad, "--require-base"))[0] == 1
    assert twin.run(*check(bad))[0] == 0  # no in-tree baseline: first adoption
    twin.run("pkg", "--update")
    assert twin.run(*check(bad))[0] == 1  # a baseline is present: stale base


def test_update_refuses_growth_and_writes_a_reduction(twin: Twin) -> None:
    twin.source(ONE)
    assert twin.run("pkg", "--update")[0] == 0  # first adoption bootstraps
    twin.source(TWO)
    code, out = twin.run("pkg", "--update")
    assert (code, "update never loosens" in out) == (1, True)
    twin.source(CLEAN)
    assert twin.run("pkg", "--update")[0] == 0
    assert twin.run("pkg", "--update")[0] == 0  # equal total rewrites


def test_rebaseline_is_audited(twin: Twin) -> None:
    twin.source(ONE)
    assert twin.run("pkg", "--rebaseline")[0] == 1  # reason required
    code, out = twin.run("pkg", "--rebaseline", "--reason", "reset", "--source", "PL-1")
    assert (code, "(none) -> 1" in out) == (0, True)
    twin.source(THREE)
    code, out = twin.run("pkg", "--rebaseline", "--reason", "grow")
    assert (code, "1 -> 3" in out) == (0, True)


def test_writes_are_blocked_in_ci(twin: Twin, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    twin.source(ONE)
    code, out = twin.run("pkg", "--update")
    assert (code, "GITHUB_ACTIONS" in out) == (1, True)
    assert twin.run("pkg", "--update", "--allow-ci-write")[0] == 0
    assert twin.run("pkg", "--rebaseline", "--reason", "r")[0] == 1


def test_corrupt_state_fails_closed(twin: Twin) -> None:
    twin.source(ONE)
    base = twin.box.commit("base")
    (twin.box.root / ".suppression-baseline.json").write_text("{ not json")
    assert twin.run(*check(base, "--require-base"))[0] == 1
    (twin.box.root / ".suppression-baseline.json").unlink()
    (twin.box.root / ".suppression-relax.json").write_text("{}")
    assert twin.run(*check(base, "--require-base"))[0] == 1
    (twin.box.root / ".suppression-relax.json").write_text("[]")
    twin.box.commit("empty ledger")
    (twin.box.root / ".suppression-relax.json").write_text("{ not json")
    assert twin.run(*check(base, "--require-base"))[0] == 1


def test_malformed_base_ledger_fails_closed(twin: Twin) -> None:
    twin.source(ONE)
    (twin.box.root / ".suppression-relax.json").write_text("{ not json")
    base = twin.box.commit("bad ledger")
    (twin.box.root / ".suppression-relax.json").write_text("[]")
    assert twin.run(*check(base, "--require-base"))[0] == 1


def test_views_and_missing_target(twin: Twin) -> None:
    twin.source(TWO)
    for flag in ("--json", "--threshold"):
        assert twin.run("pkg", flag)[0] == 0
    assert twin.run("pkg")[0] == 0
    code, out = twin.run("nowhere", "--check")
    assert (code, "not found: nowhere" in out) == (1, True)
    assert json.loads(twin.run("pkg", "--json")[1])["total"] == 2
