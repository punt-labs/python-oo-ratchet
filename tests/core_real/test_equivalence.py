"""The new Check and Update agree with the existing OO gate on real repositories.

Each scenario builds a real git repository, runs the existing OO gate through
its CLI entry point (``oo_ratchet.oo.cli.main``), then runs the new operations
with the OO ``GatePolicy`` over in-memory ports filled from the same repository.
The verdicts must match: pass or fail, and the reasons.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from oo_ratchet.core.adapters.formats import AuditFormat
from oo_ratchet.core.application.check import Check
from oo_ratchet.core.application.update import Update
from oo_ratchet.core.domain.changes import Diff
from oo_ratchet.core.domain.verdicts import Verdict
from oo_ratchet.oo.audit import AuditLog
from oo_ratchet.oo.baseline import Baseline
from oo_ratchet.oo.cli import main
from oo_ratchet.oo.gitio import GitRepo
from tests.core.doubles import World, oo_policy
from tests.test_oo_ratchet import GOOD, GOOD_VARIANT, WORSE, GitFixture

pytestmark = pytest.mark.slow

MARKERS = (
    ("touched file(s) failed to parse", "parse-error"),
    ("not in baseline", "missing-row"),
    ("baseline out of date", "stale-row"),
    ("regression detected", "regression"),
    ("no metric improved", "no-improvement"),
)


def world_from(fx: GitFixture, base: str) -> World:
    """Fill the in-memory ports from the repository as it stands."""
    git = GitRepo(fx.root)
    w = World()
    w.history.refs = {None: base, base: base}
    w.history.baselines[base] = git.show_baseline(base)
    w.history.audits[base] = (
        AuditFormat.decode(text) if (text := git.show_audit(base)) is not None else None
    )
    diff = git.diff(base)
    w.history.diff = Diff(diff.touched, dict(diff.renames))
    w.history.short = git.short_head()
    scorer = fx.scorer()
    w.source.scores = Baseline.metrics_by_file(scorer.results)
    w.source.broken = frozenset(scorer.parse_errors)
    w.source.disk = {
        p.relative_to(fx.root).as_posix()
        for p in fx.root.rglob("*")
        if ".git" not in p.parts and p.is_file()
    }
    baseline = Baseline(fx.root)
    w.store.data = baseline.entries if baseline.exists else None
    audit = AuditLog(fx.root)
    w.audit.log = (
        list(AuditFormat.decode(audit.path.read_text())) if audit.exists else []
    )
    return w


def old_check(
    fx: GitFixture, base: str, capsys: pytest.CaptureFixture[str], *flags: str
) -> tuple[int, list[str]]:
    capsys.readouterr()
    code = main(["sub", "--check", "--base-ref", base, "--require-base", *flags])
    return code, capsys.readouterr().out.splitlines()


def old_kinds(lines: list[str]) -> list[str]:
    joined = "\n".join(lines)
    return [kind for marker, kind in MARKERS if marker in joined]


def assert_same_check(
    fx: GitFixture,
    base: str,
    capsys: pytest.CaptureFixture[str],
    *,
    passes: bool,
    allow_no_improvement: bool = False,
) -> Verdict:
    w = world_from(fx, base)
    flags = ("--allow-no-improvement",) if allow_no_improvement else ()
    code, lines = old_check(fx, base, capsys, *flags)
    new = Check(*w.args(oo_policy())).run(
        base_ref=base, require_base=True, allow_no_improvement=allow_no_improvement
    )
    assert (code == 0) is passes, lines
    assert new.passed is passes, new
    assert [f.kind for f in new.failures] == old_kinds(lines)
    for failure in new.failures:
        if failure.kind == "regression":
            assert all(f"  {s}" in lines for s in failure.subjects)
    return new


@pytest.fixture
def fx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GitFixture:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)  # the gate refuses writes in CI
    return GitFixture(tmp_path)


def start(fx: GitFixture, content: str) -> str:
    fx.write("sub/w.py", content)
    fx.snapshot("sub")
    return fx.commit("base")


def change(fx: GitFixture, content: str, message: str = "change") -> None:
    fx.write("sub/w.py", content)
    fx.snapshot("sub")
    fx.commit(message)


def test_regression_caught(fx: GitFixture, capsys: pytest.CaptureFixture[str]) -> None:
    base = start(fx, GOOD)
    change(fx, WORSE)
    assert_same_check(fx, base, capsys, passes=False)


def test_improvement_credited(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, WORSE)
    change(fx, GOOD)
    assert_same_check(fx, base, capsys, passes=True)


def test_neutral_change_fails_must_improve_unless_flagged(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, GOOD)
    change(fx, GOOD_VARIANT)
    assert_same_check(fx, base, capsys, passes=False)
    assert_same_check(fx, base, capsys, passes=True, allow_no_improvement=True)


def test_in_tree_baseline_must_be_locked(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, WORSE)
    fx.write("sub/w.py", GOOD)  # improved, but the baseline row not refreshed
    fx.commit("improve without update")
    assert_same_check(fx, base, capsys, passes=False)


def test_audited_waiver_applied(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, GOOD)
    fx.write("sub/w.py", WORSE)
    relax = fx.writer().relax(
        fx.scorer(), "sub/w.py", justify="debt", allow_ci_write=True, source="t"
    )
    assert relax.exit_code == 0
    fx.commit("relax")
    new = assert_same_check(fx, base, capsys, passes=True)
    assert new.review is not None
    assert new.review.has_waiver


def test_waiver_in_the_base_log_is_history(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    fx.write("sub/w.py", GOOD)
    fx.snapshot("sub")
    row = Baseline(fx.root).entries["sub/w.py"]
    record = {"verdict": "relaxed", "deltas": {"sub/w.py": {"max_complexity": [1, 2]}}}
    (fx.root / ".oo-audit.jsonl").write_text(json.dumps(record) + "\n")
    base = fx.commit("base with an old relaxation")
    assert row
    change(fx, WORSE)
    assert_same_check(fx, base, capsys, passes=False)


def test_reverted_file_with_rewritten_row(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, WORSE)
    change(fx, GOOD, "improve")
    fx.write("sub/w.py", WORSE)  # revert the code, keep the improved row
    fx.commit("revert code only")
    new = assert_same_check(fx, base, capsys, passes=False)
    assert [f.kind for f in new.failures] == ["stale-row"]


def test_rename_carry_catches_a_worsened_rename(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, GOOD)
    fx.move("sub/w.py", "sub/w2.py")
    fx.write("sub/w2.py", WORSE)
    fx.snapshot("sub")
    fx.commit("rename and worsen")
    assert_same_check(fx, base, capsys, passes=False)


def run_update(
    fx: GitFixture,
    base: str,
    capsys: pytest.CaptureFixture[str],
    check: Callable[[dict[str, dict[str, float]] | None, int, Verdict], None],
) -> None:
    w = world_from(fx, base)
    new = Update(*w.args(oo_policy())).run(
        base_ref=base, require_base=True, source=None
    )
    capsys.readouterr()
    code = main(["sub", "--update", "--base-ref", base, "--require-base"])
    after = json.loads((fx.root / ".oo-baseline.json").read_text())
    assert (code == 0) is new.passed
    assert w.store.data == after
    check(after, code, new)


def test_update_refuses_a_regression(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, GOOD)
    fx.write("sub/w.py", WORSE)
    fx.commit("regress, baseline row untouched")

    def expect(after: object, code: int, new: Verdict) -> None:
        assert code == 1
        assert [f.kind for f in new.failures] == ["regression"]
        assert after == json.loads(json.dumps(Baseline(fx.root).entries))

    run_update(fx, base, capsys, expect)


def test_update_writes_an_improvement(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, WORSE)
    fx.write("sub/w.py", GOOD)
    fx.commit("improve, baseline row untouched")

    def expect(after: object, code: int, new: Verdict) -> None:
        assert code == 0
        assert new.improved == 1

    run_update(fx, base, capsys, expect)


def test_update_backfills_a_missing_row(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    fx.write("sub/other.py", GOOD)
    base = start(fx, WORSE)  # the baseline row for other.py is then dropped
    rows = Baseline(fx.root).entries
    rows.pop("sub/other.py")
    fx.write_baseline(rows)
    base = fx.commit("base without other.py row")
    fx.write("sub/w.py", GOOD)
    fx.commit("improve w")

    def expect(after: object, code: int, new: Verdict) -> None:
        assert code == 0
        assert new.written == ("sub/other.py",)

    run_update(fx, base, capsys, expect)


def test_update_rename_carry(
    fx: GitFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    base = start(fx, WORSE)
    fx.move("sub/w.py", "sub/w2.py")
    fx.write("sub/w2.py", GOOD)
    fx.commit("rename and improve")

    def expect(after: object, code: int, new: Verdict) -> None:
        assert code == 0
        assert isinstance(after, dict)
        assert "sub/w.py" not in after
        assert "sub/w2.py" in after

    run_update(fx, base, capsys, expect)
