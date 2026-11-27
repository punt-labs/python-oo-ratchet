"""The OO gate on the shared core agrees with the per-gate implementation.

Each scenario builds a real git repository, copies it twice, and runs the same
argument list on both copies: through ``oo_ratchet.oo.cli.main`` (the existing
per-gate code) and through ``OoGate`` (the shared core). Exit code, stdout and
both state files (timestamps masked) must match, and the scenario states the
code and a line of output it expects so a pair of equal failures cannot pass.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from oo_ratchet.core.adapters.oogate import OoGate
from oo_ratchet.oo.cli import Options, main
from tests.test_oo_ratchet import BROKEN, GOOD, GOOD_VARIANT, WORSE, GitFixture

pytestmark = pytest.mark.slow

STATE = (".oo-baseline.json", ".oo-audit.jsonl")
STAMP = re.compile(r'"ts":"[^"]*"')


@dataclass(frozen=True)
class Run:
    """What one invocation produced."""

    code: int
    out: str
    state: dict[str, str | None]


@pytest.fixture
def fx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GitFixture:
    (tmp_path / "work").mkdir()
    monkeypatch.chdir(tmp_path / "work")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)  # CI refuses writes
    return GitFixture(tmp_path / "work")


def observe(root: Path, code: int, out: str) -> Run:
    state: dict[str, str | None] = {}
    for name in STATE:
        path = root / name
        state[name] = STAMP.sub('"ts":"T"', path.read_text()) if path.exists() else None
    return Run(code, out.replace(str(root), "<root>"), state)


def run_old(root: Path, capsys: pytest.CaptureFixture[str], argv: list[str]) -> Run:
    os.chdir(root)
    capsys.readouterr()
    code = main(argv)
    return observe(root, code, capsys.readouterr().out)


def run_new(root: Path, capsys: pytest.CaptureFixture[str], argv: list[str]) -> Run:
    os.chdir(root)
    capsys.readouterr()
    lines, code = OoGate(Options.parse(argv)).run()
    return observe(root, code, "".join(f"{line}\n" for line in lines))


def both(
    fx: GitFixture,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    *,
    code: int,
    has: str = "",
    same_text: bool = True,
) -> Run:
    """Run ``argv`` on two copies of the repository and compare the results."""
    parent = fx.root.parent
    copies = [parent / "old", parent / "new"]
    for copy in copies:
        shutil.rmtree(copy, ignore_errors=True)
        shutil.copytree(fx.root, copy, symlinks=True)
    old = run_old(copies[0], capsys, argv)
    new = run_new(copies[1], capsys, argv)
    os.chdir(fx.root)
    assert old.code == code, old.out
    assert new.code == code, (new.out, old.out)
    assert has in old.out, old.out
    assert new.state == old.state
    if same_text:
        assert new.out == old.out
    else:
        assert "FAIL" in new.out
    return old


def check(
    base: str, *flags: str, require: bool = True, target: str = "sub"
) -> list[str]:
    argv = [target, "--check", "--base-ref", base, *flags]
    return [*argv, "--require-base"] if require else argv


def start(fx: GitFixture, content: str) -> str:
    fx.write("sub/w.py", content)
    fx.snapshot("sub")
    return fx.commit("base")


def change(fx: GitFixture, content: str, message: str = "change") -> None:
    fx.write("sub/w.py", content)
    fx.snapshot("sub")
    fx.commit(message)


# --- check ------------------------------------------------------------------


def test_check_regression(fx: GitFixture, capsys: pytest.CaptureFixture[str]) -> None:
    base = start(fx, GOOD)
    change(fx, WORSE)
    both(fx, capsys, check(base), code=1, has="FAIL: regression detected")


def test_check_improvement(fx: GitFixture, capsys: pytest.CaptureFixture[str]) -> None:
    base = start(fx, WORSE)
    change(fx, GOOD)
    both(fx, capsys, check(base), code=0, has="PASS: at least one metric improved")


def test_check_neutral_change_needs_the_flag(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, GOOD)
    change(fx, GOOD_VARIANT)
    both(fx, capsys, check(base), code=1, has="no metric improved")
    both(
        fx,
        capsys,
        check(base, "--allow-no-improvement"),
        code=0,
        has="must-improve gate waived",
    )


def test_check_baseline_not_locked(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, WORSE)
    fx.write("sub/w.py", GOOD)
    fx.commit("improve without update")
    both(fx, capsys, check(base), code=1, has="baseline out of date -- run make")


def test_check_new_file_without_row(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, GOOD)
    fx.write("sub/new.py", GOOD)
    fx.commit("add a file, no row")
    both(fx, capsys, check(base), code=1, has="not in baseline")


def test_check_new_file_with_row_is_judged_by_target(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, GOOD)
    fx.write("sub/new.py", WORSE)
    fx.snapshot("sub")
    fx.commit("add a failing file")
    both(fx, capsys, check(base), code=0)
    fx.write("sub/third.py", GOOD)
    fx.snapshot("sub")
    fx.commit("add a clean file")
    both(fx, capsys, check(base), code=0, has="NEW")


def test_check_relax_waives(fx: GitFixture, capsys: pytest.CaptureFixture[str]) -> None:
    base = start(fx, GOOD)
    fx.write("sub/w.py", WORSE)
    both(
        fx,
        capsys,
        ["sub", "--relax", "sub/w.py", "--justify", "debt", "--source", "t"],
        code=0,
        has="Relaxed sub/w.py (reason: debt)",
    )
    assert main(["sub", "--relax", "sub/w.py", "--justify", "debt"]) == 0
    fx.commit("relax")
    both(fx, capsys, check(base), code=0, has="RELAXED")


def test_check_relaxation_in_base_log_is_history(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    fx.write("sub/w.py", GOOD)
    fx.snapshot("sub")
    record = {"verdict": "relaxed", "deltas": {"sub/w.py": {"max_complexity": [1, 2]}}}
    (fx.root / ".oo-audit.jsonl").write_text(json.dumps(record) + "\n")
    base = fx.commit("base with an old relaxation")
    change(fx, WORSE)
    both(fx, capsys, check(base), code=1, has="regression detected")


def test_check_reverted_file_keeps_rewritten_row(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, WORSE)
    change(fx, GOOD, "improve")
    fx.write("sub/w.py", WORSE)
    fx.commit("revert code only")
    both(fx, capsys, check(base), code=1, has="baseline out of date")


def test_check_rename_carries_the_base_row(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, GOOD)
    fx.move("sub/w.py", "sub/w2.py")
    fx.write("sub/w2.py", WORSE)
    fx.snapshot("sub")
    fx.commit("rename and worsen")
    both(fx, capsys, check(base), code=1, has="regression detected")


def test_check_parse_error_in_touched_file(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, GOOD)
    fx.write("sub/w.py", BROKEN)
    fx.commit("break it")
    both(fx, capsys, check(base), code=1, has="failed to parse")


def test_check_no_python_touched(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, GOOD)
    fx.write("README.md", "docs\n")
    fx.commit("docs")
    both(fx, capsys, check(base), code=0, has="No Python files touched")


def test_check_untouched_with_rewritten_stale_row(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, GOOD)
    fx.write_baseline({"sub/w.py": {"max_complexity": 9.0}})
    fx.write("README.md", "docs\n")
    fx.commit("hand-edit a row")
    both(fx, capsys, check(base), code=1, has="baseline out of date")


# --- check: the base --------------------------------------------------------


def test_check_base_does_not_resolve(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    start(fx, GOOD)
    both(
        fx,
        capsys,
        check("nosuchref"),
        code=1,
        has="base ref unresolvable and --require-base is set",
    )
    both(fx, capsys, check("nosuchref", require=False), code=1, has="fetch origin/main")


def test_check_first_adoption_passes(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    fx.write("sub/w.py", GOOD)
    fx.commit("no baseline anywhere")
    both(
        fx,
        capsys,
        ["sub", "--check"],
        code=0,
        has="No base and no in-tree baseline -- first-adoption bootstrap pass",
    )


def test_check_base_without_baseline(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    fx.write("sub/w.py", GOOD)
    base = fx.commit("before adoption")
    fx.snapshot("sub")
    fx.commit("adopt")
    both(
        fx,
        capsys,
        check(base, require=False),
        code=0,
        has="No baseline at base or origin/main tip -- first-adoption",
    )
    both(
        fx,
        capsys,
        check(base, "--tripwire", require=False),
        code=0,
        has="Base predates baseline adoption on push tripwire",
    )


def test_check_base_without_baseline_and_baseline_on_main(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    fx.write("sub/w.py", GOOD)
    base = fx.commit("before adoption")
    fx.snapshot("sub")
    tip = fx.commit("adopt")
    fx.set_origin_main(tip)
    both(
        fx,
        capsys,
        check(base, require=False),
        code=1,
        has="base commit predates baseline adoption; rebase onto current main",
    )


def test_check_tripwire_without_in_tree_baseline(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    fx.write("sub/w.py", GOOD)
    base = fx.commit("no baseline")
    both(
        fx,
        capsys,
        check(base, "--tripwire", require=False),
        code=1,
        has="--tripwire with no baseline on main; only the adoption commit",
    )


def test_check_base_without_baseline_unresolvable_tip(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    fx.write("sub/w.py", GOOD)
    base = fx.commit("no baseline")
    fx.snapshot("sub")
    fx.commit("adopt")
    both(
        fx,
        capsys,
        check(base, require=False),
        code=0,
        has="No baseline at base or origin/main tip",
    )


def test_check_empty_base_baseline(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    fx.write("sub/w.py", GOOD)
    fx.write_baseline({})
    base = fx.commit("empty baseline")
    fx.snapshot("sub")
    fx.commit("fill it")
    both(fx, capsys, check(base), code=1, has="base baseline is empty")
    both(fx, capsys, check(base, require=False), code=0)


def test_check_corrupt_state_fails_closed(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    fx.write("sub/w.py", GOOD)
    fx.write(".oo-baseline.json", '{"sub/w.py": "garbage"}')
    base = fx.commit("nested non-dict base baseline")
    fx.snapshot("sub")
    fx.write("sub/w.py", WORSE)
    fx.commit("valid in-tree baseline and regress")
    both(fx, capsys, check(base), code=1, has="FAIL", same_text=False)
    fx.write(".oo-baseline.json", "{ not json")
    both(fx, capsys, check(base), code=1, has="unreadable baseline file")
    fx.write(".oo-baseline.json", "[1]")
    both(fx, capsys, check(base), code=1, has="non-dict baseline file")
    fx.write(".oo-baseline.json", '{"sub/w.py": "x"}')
    both(fx, capsys, check(base), code=1, has="non-dict entry in baseline file")
    fx.write(".oo-baseline.json", '{"sub/w.py": {"module_size": true}}')
    both(fx, capsys, check(base), code=1, has="non-numeric metric in baseline file")


def test_corrupt_audit_log_fails_closed(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, GOOD)
    change(fx, WORSE)
    fx.write(".oo-audit.jsonl", "<<<<<<< not json\n")
    fx.commit("conflict marker")
    both(fx, capsys, check(base), code=1, has="malformed audit entry")


def test_target_missing_and_unscorable(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, GOOD)
    both(fx, capsys, check(base, target="nope"), code=1, has="Not found: nope")
    fx.write("sub/bad.py", BROKEN)
    both(
        fx,
        capsys,
        check(base, target="sub/bad.py"),
        code=1,
        has="FAIL: cannot score sub/bad.py",
    )


# --- update, reconcile ------------------------------------------------------


def update(base: str, *flags: str) -> list[str]:
    return ["sub", "--update", "--base-ref", base, "--require-base", *flags]


def test_update_refuses_a_regression(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, GOOD)
    fx.write("sub/w.py", WORSE)
    fx.commit("regress")
    both(fx, capsys, update(base), code=1, has="REFUSED (1 files):")


def test_update_writes_an_improvement(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, WORSE)
    fx.write("sub/w.py", GOOD)
    fx.commit("improve")
    both(fx, capsys, update(base, "--source", "PR-1"), code=0, has="files improved: 1")


def test_update_backfills_a_missing_row(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    fx.write("sub/other.py", GOOD)
    start(fx, WORSE)
    rows = json.loads((fx.root / ".oo-baseline.json").read_text())
    rows.pop("sub/other.py")
    fx.write_baseline(rows)
    base = fx.commit("without other.py")
    fx.write("sub/w.py", GOOD)
    fx.commit("improve w")
    both(fx, capsys, update(base), code=0, has="  backfilled: sub/other.py")


def test_update_carries_a_rename_and_drops_deleted_rows(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    fx.write("sub/gone.py", GOOD)
    base = start(fx, WORSE)
    fx.move("sub/w.py", "sub/w2.py")
    fx.write("sub/w2.py", GOOD)
    (fx.root / "sub/gone.py").unlink()
    fx.commit("rename, improve, delete")
    both(fx, capsys, update(base), code=0, has="files removed:  2")


def test_update_refuses_a_worsened_rename(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, GOOD)
    fx.move("sub/w.py", "sub/w2.py")
    fx.write("sub/w2.py", WORSE)
    fx.commit("rename and worsen")
    both(fx, capsys, update(base), code=1, has="REFUSED")


def test_update_refuses_an_unparseable_file(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, GOOD)
    fx.write("sub/w.py", BROKEN)
    fx.commit("break it")
    both(fx, capsys, update(base), code=1, has="1 unparseable, baseline kept")


def test_update_without_a_base(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    start(fx, GOOD)
    both(
        fx,
        capsys,
        ["sub", "--update", "--base-ref", "nosuchref", "--require-base"],
        code=1,
        has="base ref unresolvable and --require-base is set",
    )
    both(
        fx,
        capsys,
        ["sub", "--update", "--base-ref", "nosuchref"],
        code=1,
        has="or use --reconcile for an intentional whole-tree sweep",
    )


def test_update_first_adoption_bootstraps(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    fx.write("sub/w.py", GOOD)
    fx.commit("no baseline")
    both(fx, capsys, ["sub", "--update"], code=0, has="Baseline updated")


def test_writes_are_refused_under_ci(
    fx: GitFixture, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    base = start(fx, WORSE)
    fx.write("sub/w.py", GOOD)
    fx.commit("improve")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    refusal = "refusing to write baseline under GITHUB_ACTIONS"
    both(fx, capsys, update(base), code=1, has=refusal)
    both(fx, capsys, ["sub", "--rebaseline"], code=1, has=refusal)
    both(fx, capsys, ["sub", "--reconcile"], code=1, has=refusal)
    both(fx, capsys, ["sub", "--relax", "sub/w.py", "--justify", "x"], code=1)
    both(
        fx,
        capsys,
        ["sub", "--rebaseline-files", "sub/w.py", "--reason", "x"],
        code=1,
        has=refusal,
    )
    both(fx, capsys, update(base, "--allow-ci-write"), code=0, has="Baseline updated")


def test_reconcile_prunes_and_refuses(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    fx.write("sub/gone.py", GOOD)
    start(fx, GOOD)
    (fx.root / "sub/gone.py").unlink()
    fx.write("sub/w.py", WORSE)
    both(fx, capsys, ["sub", "--reconcile"], code=1, has="REFUSED (1 files):")
    fx.write("sub/w.py", GOOD)
    both(fx, capsys, ["sub", "--reconcile"], code=0, has="files removed:  1")


def test_reconcile_with_a_base_and_a_rename(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    tip = start(fx, WORSE)
    fx.set_origin_main(tip)
    fx.move("sub/w.py", "sub/w2.py")
    fx.write("sub/w2.py", GOOD)
    fx.commit("rename and improve")
    both(fx, capsys, ["sub", "--reconcile"], code=0, has="files improved: 1")


def test_reconcile_without_a_base(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    start(fx, GOOD)
    both(
        fx,
        capsys,
        ["sub", "--reconcile"],
        code=1,
        has="cannot resolve base for reconcile",
    )


def test_reconcile_first_adoption(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    fx.write("sub/w.py", GOOD)
    fx.commit("nothing yet")
    both(fx, capsys, ["sub", "--reconcile"], code=0, has="Baseline updated")


# --- relax, bless, rebaseline -----------------------------------------------


def test_relax_refusals(fx: GitFixture, capsys: pytest.CaptureFixture[str]) -> None:
    start(fx, GOOD)
    both(
        fx,
        capsys,
        ["sub", "--relax", "sub/w.py"],
        code=1,
        has="--relax requires a non-empty --justify",
    )
    both(
        fx,
        capsys,
        ["sub", "--relax", "sub/nope.py", "--justify", "x"],
        code=1,
        has="not a scored file: sub/nope.py",
    )
    both(
        fx,
        capsys,
        ["sub", "--relax", "sub/w.py", "--justify", "x"],
        code=1,
        has="nothing to relax for sub/w.py",
    )
    fx.write("sub/new.py", GOOD)
    both(
        fx,
        capsys,
        ["sub", "--relax", "sub/new.py", "--justify", "x"],
        code=1,
        has="has no baseline entry to relax",
    )


def test_relax_writes_the_loosened_row(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    start(fx, GOOD)
    fx.write("sub/w.py", WORSE)
    both(
        fx,
        capsys,
        ["sub", "--relax", "sub/w.py", "--justify", "debt", "--source", "PR-2"],
        code=0,
        has="  baseline: <root>/.oo-baseline.json",
    )


def bless(*paths: str, reason: str = "needed") -> list[str]:
    return ["sub", "--rebaseline-files", ",".join(paths), "--reason", reason]


def test_bless_accepts_and_audits(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    start(fx, GOOD)
    fx.write("sub/w.py", WORSE)
    both(
        fx,
        capsys,
        bless("sub/w.py", "./sub/w.py", reason="why"),
        code=0,
        has="Baseline blessed for 2 file(s) (reason: why):",
    )


def test_bless_refuses_an_over_cap_regression(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    fx.write("sub/w.py", GOOD)
    fx.write("sub/z.py", GOOD)
    start(fx, GOOD)
    nested = "".join(f"{'    ' * (i + 2)}if self._n > {i}:\n" for i in range(12))
    body = WORSE.replace(
        '        return "neg"\n',
        f'        return "neg"\n\n    def deep(self) -> int:\n{nested}'
        f"{'    ' * 14}return 1\n        return 0\n",
    )
    fx.write("sub/w.py", body)
    both(
        fx,
        capsys,
        bless("sub/w.py", "sub/z.py", "sub/absent.py"),
        code=1,
        has="REFUSED (",
    )


def test_bless_guards_run_before_scoring(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    start(fx, GOOD)
    both(
        fx,
        capsys,
        ["nope", "--rebaseline-files", "sub/w.py", "--reason", " "],
        code=1,
        has="--rebaseline-files requires --reason <text>",
    )
    both(
        fx,
        capsys,
        ["nope", "--rebaseline-files", ",", "--reason", "x"],
        code=1,
        has="--rebaseline-files requires at least one path",
    )


def test_rebaseline_resets_the_baseline(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    fx.write("sub/gone.py", GOOD)
    start(fx, GOOD)
    (fx.root / "sub/gone.py").unlink()
    fx.write("sub/w.py", WORSE)
    both(
        fx,
        capsys,
        ["sub", "--rebaseline", "--source", "PR-3"],
        code=0,
        has="files scored: 1",
    )


# --- views ------------------------------------------------------------------


def test_views(fx: GitFixture, capsys: pytest.CaptureFixture[str]) -> None:
    start(fx, GOOD)
    both(fx, capsys, ["sub", "--json"], code=0, has='"per_file"')
    both(fx, capsys, ["sub"], code=0, has="Metric")
    both(fx, capsys, ["sub", "--threshold"], code=0, has="Per-file breakdown")
    both(fx, capsys, ["sub", "--audit-completeness"], code=0, has="baseline complete")
    both(fx, capsys, ["sub", "--log"], code=0, has="No audit log found")
    both(fx, capsys, ["sub", "--rebaseline"], code=0)
    fx.write("sub/w.py", WORSE)
    fx.write("sub/extra.py", GOOD)
    both(
        fx,
        capsys,
        ["sub", "--audit-completeness"],
        code=1,
        has="files missing from baseline",
    )
    fx.write("sub/w.py", BROKEN)
    both(fx, capsys, ["sub", "--json"], code=1, has="error")


def test_log_lists_the_history(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    start(fx, GOOD)
    fx.write("sub/w.py", WORSE)
    capsys.readouterr()
    assert main(["sub", "--rebaseline"]) == 0
    both(fx, capsys, ["sub", "--log"], code=0, has="rebaseline")
