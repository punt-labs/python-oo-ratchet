"""Integration tests for the merge-base coupling ratchet against tmp git repos.

The load-bearing behavior is merge-base scoping: a coupling regression made in an
earlier commit of a multi-commit PR and not re-touched in the final commit must
still be scored. The old ``HEAD~1..HEAD`` scoping missed exactly that case. The
rest covers the regression-only verdict, scoped never-loosen update, fail-closed
git/baseline handling, the CI-write guard, and the trivial-pass path.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Self

import pytest

from oo_ratchet.core.adapters.auditview import AuditView
from oo_ratchet.core.adapters.gitrepo import GitRepo
from oo_ratchet.core.adapters.jsonstore import JsonBaselineStore
from oo_ratchet.core.domain.errors import GitError, StateError
from oo_ratchet.core.domain.exits import Outcome
from oo_ratchet.coupling.cli import main
from oo_ratchet.coupling.config import CouplingConfig
from oo_ratchet.coupling.gateinput import GateInput
from oo_ratchet.coupling.scorer import CouplingScorer
from oo_ratchet.coupling.trees import score_path

BASELINE = ".oo-coupling-baseline.json"
AUDIT = ".oo-coupling-audit.jsonl"

# Every test drives a real git init/commit/checkout sequence plus a real
# tools/coupling subprocess invocation -- see the marker rationale on
# test_oo_ratchet.py and the measured timing in TESTING.md.
pytestmark = pytest.mark.slow

# A shared bulky header so git reliably detects a rename across the small metric
# change between LOW and HIGH (the body dominates the similarity score).
_BODY = (
    "from __future__ import annotations\n\n"
    "# shared body line one, present in both variants for rename detection\n"
    "# shared body line two, present in both variants for rename detection\n"
    "# shared body line three, present in both variants for rename detection\n\n"
)
# public_names == 1 (via __all__); every other metric is 0.
LOW = _BODY + '__all__ = ["x"]\n\nx = 1\n'
# public_names == 2 -> a regression against a LOW baseline.
HIGH = _BODY + '__all__ = ["x", "y"]\n\nx = 1\ny = 2\n'
# public_names == 3 -> a fresh regression against a HIGH baseline.
HIGHER = _BODY + '__all__ = ["x", "y", "z"]\n\nx = 1\ny = 2\nz = 3\n'
BROKEN = "def oops(:\n    pass\n"


class GateRun:
    """Run the coupling CLI in a fixture repository, as a person would."""

    _fx: GitFixture
    _capsys: pytest.CaptureFixture[str]
    _monkeypatch: pytest.MonkeyPatch

    def __new__(
        cls,
        fx: GitFixture,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> Self:
        self = super().__new__(cls)
        self._fx = fx
        self._capsys = capsys
        self._monkeypatch = monkeypatch
        return self

    def run(self, *argv: str) -> Outcome:
        """Run ``oo-ratchet coupling pkg ARGV`` from the repository root."""
        self._monkeypatch.chdir(self._fx.root)
        self._capsys.readouterr()
        code = main(["pkg", *argv])
        return Outcome(code, tuple(self._capsys.readouterr().out.splitlines()))

    def check(
        self, *, base_ref: str, require_base: bool, tripwire: bool = False
    ) -> Outcome:
        """Run ``--check``."""
        flags = ["--require-base"] if require_base else []
        flags += ["--tripwire"] if tripwire else []
        return self.run("--check", "--base-ref", base_ref, *flags)

    def update(
        self,
        *,
        base_ref: str,
        require_base: bool,
        allow_ci_write: bool,
        source: str | None,
    ) -> Outcome:
        """Run ``--update``."""
        flags = ["--require-base"] if require_base else []
        flags += ["--allow-ci-write"] if allow_ci_write else []
        flags += ["--source", source] if source else []
        return self.run("--update", "--base-ref", base_ref, *flags)

    def relax(
        self, file: str, *, justify: str, allow_ci_write: bool, source: str | None
    ) -> Outcome:
        """Run ``--relax``."""
        flags = ["--allow-ci-write"] if allow_ci_write else []
        flags += ["--source", source] if source else []
        return self.run("--relax", file, "--justify", justify, *flags)

    def rebaseline(
        self, *, allow_ci_write: bool, source: str | None, reason: str = ""
    ) -> Outcome:
        """Run ``--rebaseline``."""
        flags = ["--allow-ci-write"] if allow_ci_write else []
        flags += ["--reason", reason] if reason else []
        flags += ["--source", source] if source else []
        return self.run("--rebaseline", *flags)

    def bless(
        self,
        paths: list[str],
        *,
        reason: str = "r",
        base_ref: str | None = None,
        require_base: bool = False,
        allow_ci_write: bool = True,
    ) -> Outcome:
        """Run ``--rebaseline-files``."""
        flags = ["--require-base"] if require_base else []
        flags += ["--base-ref", base_ref] if base_ref else []
        flags += ["--allow-ci-write"] if allow_ci_write else []
        return self.run(
            "--rebaseline-files", ",".join(paths), "--reason", reason, *flags
        )


class GitFixture:
    """A throwaway git repo for exercising the coupling ratchet end to end."""

    _root: Path
    _gate: GateRun

    def __new__(
        cls,
        tmp: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> Self:
        self = super().__new__(cls)
        self._gate = GateRun(self, capsys, monkeypatch)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp, check=True)
        for key, val in (
            ("user.email", "t@example.com"),
            ("user.name", "Tester"),
            ("commit.gpgsign", "false"),
        ):
            subprocess.run(["git", "config", key, val], cwd=tmp, check=True)
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=tmp,
            check=True,
            capture_output=True,
            text=True,
        )
        self._root = Path(out.stdout.strip())
        return self

    @property
    def root(self) -> Path:
        """Return the repository root."""
        return self._root

    def write(self, rel: str, content: str) -> None:
        path = self._root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def write_baseline(self, data: dict[str, dict[str, float]]) -> None:
        (self._root / BASELINE).write_text(json.dumps(data, indent=2) + "\n")

    def rows(self) -> dict[str, dict[str, float]]:
        """Return the in-tree baseline rows."""
        return JsonBaselineStore(self._root / BASELINE).rows()

    def row(self, path: str) -> dict[str, float] | None:
        """Return the in-tree baseline row of ``path``, ``None`` if untracked."""
        return self.rows().get(path)

    def snapshot(self, subdir: str = "pkg") -> None:
        self.write_baseline(self.metrics(subdir))

    def commit(self, msg: str) -> str:
        subprocess.run(["git", "add", "-A"], cwd=self._root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", msg], cwd=self._root, check=True)
        return self._head()

    def move(self, src: str, dst: str) -> None:
        (self._root / dst).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "mv", src, dst], cwd=self._root, check=True)

    def checkout_new(self, branch: str) -> None:
        subprocess.run(
            ["git", "checkout", "-q", "-b", branch], cwd=self._root, check=True
        )

    def checkout(self, branch: str) -> None:
        subprocess.run(["git", "checkout", "-q", branch], cwd=self._root, check=True)

    def set_origin_main(self, sha: str) -> None:
        subprocess.run(
            ["git", "update-ref", "refs/remotes/origin/main", sha],
            cwd=self._root,
            check=True,
        )

    def _head(self) -> str:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self._root,
            check=True,
            capture_output=True,
            text=True,
        )
        return out.stdout.strip()

    def ratchet(self) -> GateRun:
        return self._gate

    def writer(self) -> GateRun:
        return self._gate

    def metrics(self, subdir: str = "pkg") -> dict[str, dict[str, float]]:
        """Return the scored metrics of ``subdir``, as a baseline holds them."""
        scorer = score_path(self._root / subdir, self._root)
        return GateInput(CouplingConfig(), scorer).measurement.metrics()

    def scorer(self, subdir: str = "pkg") -> CouplingScorer:
        return score_path(self._root / subdir, self._root)


@pytest.fixture
def fx(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> GitFixture:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return GitFixture(tmp_path, capsys, monkeypatch)


class TestMergeBaseScoping:
    """The core fix: score regressions anywhere in the PR, not just the tip."""

    def test_regression_in_earlier_commit_is_caught(self, fx: GitFixture) -> None:
        # a.py regresses in commit 1; commit 2 touches only b.py. The merge-base
        # diff (fork..worktree) still includes a.py, so its regression fails.
        fx.write("pkg/a.py", LOW)
        fx.write("pkg/b.py", LOW)
        fx.snapshot()
        fork = fx.commit("fork")
        fx.checkout_new("feature")
        fx.write("pkg/a.py", HIGH)  # regression, in the EARLIER commit
        fx.commit("regress a")
        fx.write("pkg/b.py", LOW + "# touched, no metric change\n")
        fx.commit("touch b only")
        outcome = fx.ratchet().check(base_ref=fork, require_base=True)
        assert outcome.exit_code == 1
        assert any(
            "pkg/a.py" in line and "public_names" in line for line in outcome.lines
        )

    def test_per_commit_scope_would_have_missed_it(self, fx: GitFixture) -> None:
        # The same tree, scoped HEAD~1..HEAD (the old behavior), only sees b.py --
        # a.py's regression slips through. This documents the hole the fix closes.
        fx.write("pkg/a.py", LOW)
        fx.write("pkg/b.py", LOW)
        fx.snapshot()
        fx.commit("fork")
        fx.checkout_new("feature")
        fx.write("pkg/a.py", HIGH)
        fx.commit("regress a")
        fx.write("pkg/b.py", LOW + "# touched\n")
        fx.commit("touch b only")
        outcome = fx.ratchet().check(base_ref="HEAD~1", require_base=True)
        assert outcome.exit_code == 0  # old per-commit scope misses a.py


class TestBaseCompare:
    """Regression-only verdict against the in-tree baseline."""

    def test_steady_passes(self, fx: GitFixture) -> None:
        fx.write("pkg/a.py", LOW)
        fx.snapshot()
        base = fx.commit("base")
        fx.write("pkg/a.py", LOW + "# comment\n")  # no metric change
        fx.commit("touch")
        outcome = fx.ratchet().check(base_ref=base, require_base=True)
        assert outcome.exit_code == 0

    def test_regression_fails(self, fx: GitFixture) -> None:
        fx.write("pkg/a.py", LOW)
        fx.snapshot()
        base = fx.commit("base")
        fx.write("pkg/a.py", HIGH)
        fx.commit("regress")
        outcome = fx.ratchet().check(base_ref=base, require_base=True)
        assert outcome.exit_code == 1
        assert any("regression" in line for line in outcome.lines)

    def test_new_file_is_info_not_regression(self, fx: GitFixture) -> None:
        fx.write("pkg/a.py", LOW)
        fx.snapshot()
        base = fx.commit("base")
        fx.write("pkg/new.py", HIGH)  # new, not in baseline
        fx.commit("add new")
        outcome = fx.ratchet().check(base_ref=base, require_base=True)
        assert outcome.exit_code == 0

    def test_no_src_touched_is_trivial_pass(self, fx: GitFixture) -> None:
        fx.write("pkg/a.py", LOW)
        fx.snapshot()
        base = fx.commit("base")
        fx.write("notes.txt", "unrelated change\n")  # not a scored .py
        fx.commit("touch non-source")
        outcome = fx.ratchet().check(base_ref=base, require_base=True)
        assert outcome.exit_code == 0
        assert any("No scored Python files touched" in line for line in outcome.lines)


class TestBaseCommitAuthoritative:
    """The comparison baseline is read from the base commit, not the worktree."""

    def test_in_tree_baseline_edit_cannot_launder_regression(
        self, fx: GitFixture
    ) -> None:
        # A PR regresses a.py AND rewrites the in-tree baseline to match. The
        # check reads the baseline from the base commit blob, so the regression
        # is still caught despite the hand-edit.
        fx.write("pkg/a.py", LOW)
        fx.snapshot()
        base = fx.commit("base")  # base-commit baseline: a.py public_names=1
        fx.write("pkg/a.py", HIGH)  # regression
        fx.write_baseline(fx.metrics())
        fx.commit("regress and launder the in-tree baseline")
        outcome = fx.ratchet().check(base_ref=base, require_base=True)
        assert outcome.exit_code == 1
        assert any("public_names" in line for line in outcome.lines)

    def test_empty_base_baseline_fails_closed(self, fx: GitFixture) -> None:
        # An empty {} baseline at the base (truncated write / bad merge) makes
        # every touched file look new -> would pass. Under require_base, fail
        # closed exactly like a missing baseline.
        fx.write("pkg/a.py", LOW)
        fx.write_baseline({})
        base = fx.commit("base with empty baseline")
        fx.write("pkg/a.py", HIGH)
        fx.commit("regress")
        outcome = fx.ratchet().check(base_ref=base, require_base=True)
        assert outcome.exit_code == 1
        assert any("empty" in line for line in outcome.lines)

    def test_empty_base_baseline_local_passes_clean(self, fx: GitFixture) -> None:
        # Empty {} base baseline without --require-base flows through
        # _check_against: a clean touched file is new/INFO -> no regression ->
        # pass, matching the OO ratchet (not a bare short-circuit pass).
        fx.write("pkg/a.py", LOW)
        fx.write_baseline({})
        base = fx.commit("base with empty baseline")
        fx.write("pkg/a.py", HIGH)  # changed, but new-vs-empty-base is INFO
        fx.commit("change")
        outcome = fx.ratchet().check(base_ref=base, require_base=False)
        assert outcome.exit_code == 0

    def test_empty_base_baseline_local_still_parses(self, fx: GitFixture) -> None:
        # Empty {} base baseline without --require-base still runs the touched-file
        # parse check: an unparseable touched file fails, matching the OO ratchet.
        fx.write("pkg/a.py", LOW)
        fx.write_baseline({})
        base = fx.commit("base with empty baseline")
        fx.write("pkg/a.py", BROKEN)  # unparseable, touched
        fx.commit("break")
        outcome = fx.ratchet().check(base_ref=base, require_base=False)
        assert outcome.exit_code == 1
        assert any("failed to parse" in line for line in outcome.lines)


class TestScopedUpdate:
    """Scoped update writes improvements but never loosens."""

    def test_update_refuses_regression(self, fx: GitFixture) -> None:
        fx.write("pkg/a.py", LOW)
        fx.snapshot()
        base = fx.commit("base")
        fx.write("pkg/a.py", HIGH)  # worse than the in-tree baseline
        outcome = fx.writer().update(
            base_ref=base,
            require_base=False,
            allow_ci_write=True,
            source=None,
        )
        assert outcome.exit_code == 1
        entry = fx.row("pkg/a.py")
        assert entry is not None
        assert entry["public_names"] == 1.0  # unloosened

    def test_update_writes_improvement(self, fx: GitFixture) -> None:
        fx.write("pkg/a.py", HIGH)
        fx.snapshot()
        base = fx.commit("base")
        fx.write("pkg/a.py", LOW)  # improved (fewer public names)
        outcome = fx.writer().update(
            base_ref=base,
            require_base=False,
            allow_ci_write=True,
            source=None,
        )
        assert outcome.exit_code == 0
        entry = fx.row("pkg/a.py")
        assert entry is not None
        assert entry["public_names"] == 1.0

    def test_update_unresolvable_base_with_baseline_fails_closed(
        self, fx: GitFixture
    ) -> None:
        fx.write("pkg/a.py", LOW)
        fx.snapshot()
        fx.commit("base")
        before = dict(fx.rows())
        outcome = fx.writer().update(
            base_ref="0" * 40,
            require_base=False,
            allow_ci_write=True,
            source=None,
        )
        assert outcome.exit_code == 1
        assert any("cannot resolve base" in line for line in outcome.lines)
        assert fx.rows() == before  # no whole-tree sweep

    def test_update_bootstrap_no_baseline_whole_tree(self, fx: GitFixture) -> None:
        fx.write("pkg/a.py", LOW)
        fx.commit("pre-adoption, no baseline")
        outcome = fx.writer().update(
            base_ref="0" * 40,
            require_base=False,
            allow_ci_write=True,
            source=None,
        )
        assert outcome.exit_code == 0
        assert fx.row("pkg/a.py") is not None


class TestRelaxWaiver:
    """A relaxed, locked coupling regression is waived by check."""

    def test_relax_then_check_waives(self, fx: GitFixture) -> None:
        fx.write("pkg/a.py", LOW)
        fx.snapshot()
        base = fx.commit("base")
        fx.write("pkg/a.py", HIGH)  # regresses public_names vs base
        relax = fx.writer().relax(
            "pkg/a.py",
            justify="accepted coupling debt",
            allow_ci_write=True,
            source="vox-x #1",
        )
        assert relax.exit_code == 0
        fx.commit("relax")
        outcome = fx.ratchet().check(base_ref=base, require_base=True)
        assert outcome.exit_code == 0

    def test_relax_requires_justification(self, fx: GitFixture) -> None:
        fx.write("pkg/a.py", LOW)
        fx.snapshot()
        fx.commit("base")
        outcome = fx.writer().relax(
            "pkg/a.py", justify="  ", allow_ci_write=True, source=None
        )
        assert outcome.exit_code == 1

    def test_relax_untracked_file_writes_no_relaxation(self, fx: GitFixture) -> None:
        # A file with no prior baseline entry has nothing to loosen: relax must
        # refuse, forge no "relaxed" audit line, and add no waivable pair.
        fx.write("pkg/a.py", LOW)  # no snapshot -> no baseline entry for a.py
        fx.commit("base")
        outcome = fx.writer().relax(
            "pkg/a.py", justify="x", allow_ci_write=True, source=None
        )
        assert outcome.exit_code == 1
        assert any(
            "--update" in line or "--rebaseline" in line for line in outcome.lines
        )
        assert fx.row("pkg/a.py") is None  # not added
        audit_path = fx.root / ".oo-coupling-audit.jsonl"
        assert not audit_path.exists() or "relaxed" not in audit_path.read_text()

    def test_relax_no_loosening_refuses(self, fx: GitFixture) -> None:
        # A file whose metrics all meet/beat its baseline has nothing to loosen:
        # relax refuses, writes no relaxed audit line, leaves the baseline as is.
        fx.write("pkg/a.py", LOW)
        fx.snapshot()  # baseline == current, nothing worse
        fx.commit("base")
        before = dict(fx.rows())
        outcome = fx.writer().relax(
            "pkg/a.py", justify="x", allow_ci_write=True, source=None
        )
        assert outcome.exit_code == 1
        assert any("nothing to relax" in line for line in outcome.lines)
        assert fx.rows() == before  # unchanged
        audit_path = fx.root / ".oo-coupling-audit.jsonl"
        assert not audit_path.exists() or "relaxed" not in audit_path.read_text()

    def test_historical_relaxation_does_not_waive_fresh_regression(
        self, fx: GitFixture
    ) -> None:
        # A relaxation committed at base must not bless a fresh regression that a
        # later --rebaseline merely re-locks to a worse value.
        fx.write("pkg/a.py", LOW)
        fx.snapshot()  # baseline public_names=1
        fx.write("pkg/a.py", HIGH)  # regresses vs baseline -> relax loosens it
        fx.writer().relax(
            "pkg/a.py",
            justify="historical",
            allow_ci_write=True,
            source=None,
        )
        base = fx.commit("adopt with historical relaxation")
        fx.write("pkg/a.py", HIGHER)  # fresh regression: public_names 3 vs base 2
        fx.writer().rebaseline(allow_ci_write=True, source=None)
        fx.commit("regress then rebaseline")
        outcome = fx.ratchet().check(base_ref=base, require_base=True)
        assert outcome.exit_code == 1
        assert any("regression" in line for line in outcome.lines)

    def test_relaxing_one_metric_does_not_waive_another(self, fx: GitFixture) -> None:
        # Relax M1 (public_names); a fresh regression of M2 (efferent_coupling) on
        # the same file, though locked in-tree, must NOT be waived.
        fx.write("pkg/a.py", HIGH)
        current = fx.metrics()["pkg/a.py"]
        base_metrics = {
            **current,
            "public_names": current["public_names"] - 1,
            "efferent_coupling": current["efferent_coupling"] - 1,
        }
        # base commit carries a different file body so a.py lands in the diff;
        # its baseline blob is the hand-built stricter metrics.
        fx.write("pkg/a.py", LOW)
        fx.write_baseline({"pkg/a.py": base_metrics})
        base = fx.commit("base with both metrics stricter")
        # HEAD: restore HIGH, lock in-tree baseline to current; relax ONLY M1.
        fx.write("pkg/a.py", HIGH)
        fx.write_baseline({"pkg/a.py": current})
        relaxed = {
            "verdict": "relaxed",
            "deltas": {
                "pkg/a.py": {
                    "public_names": [
                        base_metrics["public_names"],
                        current["public_names"],
                    ]
                }
            },
        }
        fx.write(".oo-coupling-audit.jsonl", json.dumps(relaxed) + "\n")
        fx.commit("lock and relax public_names only")
        outcome = fx.ratchet().check(base_ref=base, require_base=True)
        assert outcome.exit_code == 1
        assert any("efferent_coupling" in line for line in outcome.lines)


class TestRenameCarry:
    """A renamed file inherits its predecessor's baseline entry."""

    def test_rename_regression_is_caught(self, fx: GitFixture) -> None:
        # The in-tree baseline still keys the metrics under old.py; new.py falls
        # back to old.py's entry via the diff's rename map, so a worsened rename
        # cannot launder its history as a brand-new file.
        fx.write("pkg/old.py", LOW)
        fx.snapshot()
        base = fx.commit("base")
        fx.move("pkg/old.py", "pkg/new.py")
        fx.write("pkg/new.py", HIGH)  # worsened during the rename
        fx.commit("rename and worsen")
        outcome = fx.ratchet().check(base_ref=base, require_base=True)
        assert outcome.exit_code == 1
        assert any("public_names" in line for line in outcome.lines)

    def test_update_refuses_worsened_rename_and_keeps_source(
        self, fx: GitFixture
    ) -> None:
        # update() carries old.py's baseline entry across the rename: a worsened
        # new.py is refused (not written) and the old rename-source entry is
        # preserved, so a second run still refuses -- no laundering across update.
        fx.write("pkg/old.py", LOW)
        fx.snapshot()
        base = fx.commit("base")
        fx.move("pkg/old.py", "pkg/new.py")
        fx.write("pkg/new.py", HIGH)  # regressed vs old.py's carried baseline
        first = fx.writer().update(
            base_ref=base,
            require_base=False,
            allow_ci_write=True,
            source=None,
        )
        assert first.exit_code == 1
        assert any("regressed" in line for line in first.lines)
        assert fx.row("pkg/new.py") is None  # not written
        assert fx.row("pkg/old.py") is not None  # carry kept
        second = fx.writer().update(
            base_ref=base,
            require_base=False,
            allow_ci_write=True,
            source=None,
        )
        assert second.exit_code == 1  # still refuses on a second pass
        assert fx.row("pkg/new.py") is None


class TestCiWriteGuard:
    """Mutations refuse to run under GITHUB_ACTIONS without --allow-ci-write."""

    def test_update_blocked_in_ci(
        self, fx: GitFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        fx.write("pkg/a.py", LOW)
        fx.snapshot()
        base = fx.commit("base")
        outcome = fx.writer().update(
            base_ref=base,
            require_base=False,
            allow_ci_write=False,
            source=None,
        )
        assert outcome.exit_code == 1
        assert any("GITHUB_ACTIONS" in line for line in outcome.lines)

    def test_update_allowed_with_flag_in_ci(
        self, fx: GitFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        fx.write("pkg/a.py", LOW)
        fx.snapshot()
        base = fx.commit("base")
        outcome = fx.writer().update(
            base_ref=base,
            require_base=False,
            allow_ci_write=True,
            source=None,
        )
        assert outcome.exit_code == 0


class TestTouchedParseError:
    """A touched file that fails to parse fails loud, not silently."""

    def test_broken_touched_file_fails(self, fx: GitFixture) -> None:
        fx.write("pkg/a.py", LOW)
        fx.snapshot()
        base = fx.commit("base")
        fx.write("pkg/a.py", BROKEN)  # now unparseable, still touched
        fx.commit("break")
        outcome = fx.ratchet().check(base_ref=base, require_base=True)
        assert outcome.exit_code == 1
        assert any("failed to parse" in line for line in outcome.lines)


class TestFailClosed:
    """A failed git command or corrupt baseline fails closed, not silent."""

    @staticmethod
    def _git(fx: GitFixture) -> GitRepo:
        return GitRepo(fx.root, BASELINE, AUDIT)

    def test_diff_failure_raises(self, fx: GitFixture) -> None:
        fx.write("pkg/a.py", LOW)
        fx.commit("base")
        with pytest.raises(GitError):
            self._git(fx).changes_since("refs/does/not/exist")

    def test_empty_diff_is_not_a_failure(self, fx: GitFixture) -> None:
        fx.write("pkg/a.py", LOW)
        head = fx.commit("base")
        diff = self._git(fx).changes_since(head)  # HEAD vs work tree: no changes
        assert diff.touched == frozenset()

    def test_unresolvable_base_with_require_fails_closed(self, fx: GitFixture) -> None:
        # CI path: an unresolvable base under --require-base must never pass on a
        # stale or unfetched origin/main -- fail closed.
        fx.write("pkg/a.py", LOW)
        fx.snapshot()
        fx.commit("base")
        outcome = fx.ratchet().check(base_ref="0" * 40, require_base=True)
        assert outcome.exit_code == 1
        assert any("--require-base" in line for line in outcome.lines)

    def test_unresolvable_base_with_baseline_fails_closed(self, fx: GitFixture) -> None:
        # No base resolvable + in-tree baseline present + not require_base: match
        # the OO ratchet's _no_base -- hard-fail rather than trust the
        # hand-editable in-tree file. Consistent across all three ratchets.
        fx.write("pkg/a.py", LOW)
        fx.snapshot()
        fx.commit("base")
        fx.write("pkg/a.py", HIGH)  # a regression the soft path would have caught
        outcome = fx.ratchet().check(base_ref="0" * 40, require_base=False)
        assert outcome.exit_code == 1
        assert any("origin/main" in line for line in outcome.lines)

    def test_unresolvable_base_no_baseline_is_pass(self, fx: GitFixture) -> None:
        fx.write("pkg/a.py", LOW)  # no baseline committed
        fx.commit("pre-adoption")
        outcome = fx.ratchet().check(base_ref="0" * 40, require_base=False)
        assert outcome.exit_code == 0

    def test_absent_base_baseline_unresolvable_tip_fails_closed(
        self, fx: GitFixture
    ) -> None:
        # Base resolves but carries no baseline blob; origin/main is unresolvable
        # and an in-tree baseline is present -> first-adoption cannot be confirmed,
        # so fail closed UNCONDITIONALLY (no require_base), matching oo_ratchet.
        fx.write("pkg/a.py", LOW)
        base = fx.commit("base without baseline")  # no baseline blob at base
        fx.snapshot()  # in-tree baseline now present
        fx.commit("add in-tree baseline")
        outcome = fx.ratchet().check(base_ref=base, require_base=False)
        assert outcome.exit_code == 1
        assert any("origin/main" in line for line in outcome.lines)

    def test_corrupt_in_tree_baseline_is_controlled_nonzero(
        self, fx: GitFixture
    ) -> None:
        # A corrupt .oo-coupling-baseline.json surfaces as a clean non-zero exit
        # through the CLI, not a JSONDecodeError traceback.
        fx.write("pkg/a.py", LOW)
        fx.write(BASELINE, "{ not valid json")
        fx.commit("corrupt baseline")
        assert fx.ratchet().run("--check").exit_code == 1

    @pytest.mark.parametrize(
        "text",
        [
            "{ not valid json",
            "[1, 2, 3]",
            '{"pkg/a.py": "garbage"}',
            '{"pkg/a.py": {"efferent_coupling": "5"}}',
            '{"pkg/a.py": {"efferent_coupling": true}}',
        ],
    )
    def test_malformed_in_tree_baseline_raises_a_state_error(
        self, fx: GitFixture, text: str
    ) -> None:
        # A non-dict row would make `metric not in row` a substring test and a
        # bool would compare as 0 or 1: either would skip a regression.
        fx.write(BASELINE, text)
        with pytest.raises(StateError):
            fx.rows()

    def test_non_utf8_in_tree_baseline_raises_a_state_error(
        self, fx: GitFixture
    ) -> None:
        (fx.root / BASELINE).write_bytes(b"\xff\xfe\x00")
        with pytest.raises(StateError):
            fx.rows()

    def test_non_utf8_base_baseline_blob_raises_giterror(self, fx: GitFixture) -> None:
        # A committed non-UTF8 baseline blob makes git show's text decode fail;
        # baseline_at must fail closed with GitError, not a traceback.
        fx.write("pkg/a.py", LOW)
        (fx.root / BASELINE).write_bytes(b"\xff\xfe\x00")
        head = fx.commit("non-utf8 baseline blob")
        with pytest.raises(GitError):
            self._git(fx).baseline_at(head)

    @pytest.mark.parametrize(
        "text",
        [
            "[1, 2, 3]",
            '{"pkg/a.py": "garbage"}',
            '{"pkg/a.py": {"efferent_coupling": true}}',
        ],
    )
    def test_malformed_base_baseline_raises_a_state_error(
        self, fx: GitFixture, text: str
    ) -> None:
        # Valid JSON that is not a baseline would fail open if it were read.
        fx.write("pkg/a.py", LOW)
        fx.write(BASELINE, text)
        head = fx.commit("malformed baseline blob")
        with pytest.raises(StateError):
            self._git(fx).baseline_at(head)

    def test_nested_non_dict_base_baseline_fails_closed_via_cli(
        self, fx: GitFixture
    ) -> None:
        # End-to-end: a nested-malformed base baseline must fail the gate, not
        # let a real regression pass. The in-tree baseline at HEAD is valid, so
        # only the base blob is malformed; the CLI catches the error as a
        # controlled non-zero.
        fx.write("pkg/a.py", LOW)
        fx.write(BASELINE, '{"pkg/a.py": "garbage"}')
        base = fx.commit("nested non-dict base baseline")
        fx.snapshot()  # overwrite with a valid in-tree baseline
        fx.write("pkg/a.py", HIGH)  # a regression that must not slip through
        fx.commit("valid in-tree baseline and regress")
        assert fx.ratchet().check(base_ref=base, require_base=True).exit_code == 1

    def test_non_utf8_touched_file_fails(self, fx: GitFixture) -> None:
        # A touched .py file that cannot be decoded is scored as an error (like a
        # syntax error), so the ratchet fails on it -- fail-closed, not a crash.
        fx.write("pkg/a.py", LOW)
        fx.snapshot()
        base = fx.commit("base")
        (fx.root / "pkg" / "a.py").write_bytes(b"\xff\xfe# noqa\n")  # non-UTF8, touched
        fx.commit("break encoding")
        outcome = fx.ratchet().check(base_ref=base, require_base=True)
        assert outcome.exit_code == 1
        assert any("failed to parse" in line for line in outcome.lines)

    def test_audit_view_raises_on_corrupt_audit(self, fx: GitFixture) -> None:
        fx.write(AUDIT, "not json\n")
        with pytest.raises(StateError):
            AuditView(fx.root / AUDIT, "coupling").lines()

    def test_corrupt_audit_log_is_controlled_nonzero_via_cli(
        self, fx: GitFixture
    ) -> None:
        # The --log view over a corrupt audit log surfaces a controlled non-zero,
        # not a JSONDecodeError traceback.
        fx.write("pkg/a.py", LOW)
        fx.snapshot()
        fx.write(AUDIT, "<<<< merge conflict not json\n")
        fx.commit("corrupt audit")
        assert fx.ratchet().run("--log").exit_code == 1

    def test_git_degrades_to_none_without_a_repo(self) -> None:
        gr = GitRepo(Path("/nonexistent-coupling-ratchet-xyz"), BASELINE, AUDIT)
        assert gr.root is None
        assert gr.resolve(None) is None


class TestUpdateDropsDeletedRows:
    """``--update`` drops baseline rows of files gone from the tree (PL-1734)."""

    def _stale_row_repo(self, fx: GitFixture) -> str:
        """Baseline holds a row for ``pkg/gone.py``, which no diff to base names."""
        fx.write("pkg/a.py", LOW)
        fx.snapshot()
        data = dict(fx.rows())
        data["pkg/gone.py"] = {"public_names": 3.0}
        fx.write_baseline(data)
        return fx.commit("base")

    def _update(self, fx: GitFixture, base: str) -> tuple[str, ...]:
        outcome = fx.writer().update(
            base_ref=base,
            require_base=False,
            allow_ci_write=True,
            source=None,
        )
        assert outcome.exit_code == 0
        return outcome.lines

    def test_row_of_deleted_file_is_dropped_and_reported(self, fx: GitFixture) -> None:
        base = self._stale_row_repo(fx)
        lines = self._update(fx, base)
        assert fx.row("pkg/gone.py") is None
        assert "  files removed:  1" in lines
        last = (fx.root / ".oo-coupling-audit.jsonl").read_text().splitlines()[-1]
        assert json.loads(last)["removed"] == ["pkg/gone.py"]

    def test_row_of_existing_file_is_kept(self, fx: GitFixture) -> None:
        base = self._stale_row_repo(fx)
        self._update(fx, base)
        assert fx.row("pkg/a.py") is not None

    def test_row_of_unparseable_existing_file_is_kept(self, fx: GitFixture) -> None:
        fx.write("pkg/a.py", LOW)
        fx.write("pkg/b.py", LOW)
        fx.snapshot()
        base = fx.commit("base")
        fx.write("pkg/b.py", BROKEN)
        outcome = fx.writer().update(
            base_ref=base,
            require_base=False,
            allow_ci_write=True,
            source=None,
        )
        assert outcome.exit_code == 1
        assert fx.row("pkg/b.py") is not None
