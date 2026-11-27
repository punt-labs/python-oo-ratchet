"""The GitRepo adapter against a real git repository."""

from __future__ import annotations

from pathlib import Path

import pytest

from oo_ratchet.core.adapters.gitrepo import GitRepo
from oo_ratchet.core.adapters.jsonstore import AuditFile, JsonBaselineStore
from oo_ratchet.core.adapters.sourcetree import SourceTree
from oo_ratchet.core.application.check import Check
from oo_ratchet.core.application.operation import Ports
from oo_ratchet.core.domain.errors import GitError, StateError
from oo_ratchet.core.domain.scores import Measurement, Score
from oo_ratchet.oo.baseline import Baseline
from tests.conftest import GitSandbox
from tests.core.doubles import oo_policy
from tests.test_oo_ratchet import GOOD, WORSE, GitFixture

pytestmark = pytest.mark.slow

BASELINE = ".oo-baseline.json"
AUDIT = ".oo-audit.jsonl"


def repo(sandbox: GitSandbox) -> GitRepo:
    return GitRepo(sandbox.root, BASELINE, AUDIT)


def test_baseline_and_audit_are_read_at_a_ref(git_sandbox: GitSandbox) -> None:
    git_sandbox.write(BASELINE, '{"a.py": {"m": 1.0}}\n')
    git_sandbox.write(AUDIT, '{"verdict":"relaxed","deltas":{"a.py":{"m":[1,2]}}}\n')
    sha = git_sandbox.commit("base")
    git = repo(git_sandbox)
    assert git.baseline_at(sha) == {"a.py": {"m": 1.0}}
    records = git.audit_at(sha)
    assert records is not None
    assert records[0].verdict == "relaxed"
    assert git.head() == sha[:7]
    assert git.resolve(sha) == sha
    assert git.resolve("no-such-ref") is None


def test_absent_blob_is_none_not_an_error(git_sandbox: GitSandbox) -> None:
    git_sandbox.write("x.txt", "x")
    sha = git_sandbox.commit("no baseline")
    git = repo(git_sandbox)
    assert git.baseline_at(sha) is None
    assert git.audit_at(sha) is None


def test_bad_ref_is_a_failure_not_absence(git_sandbox: GitSandbox) -> None:
    git_sandbox.write("x.txt", "x")
    git_sandbox.commit("c")
    with pytest.raises(GitError):
        repo(git_sandbox).baseline_at("nonexistent-ref-xyz")


def test_corrupt_committed_baseline_fails_closed(git_sandbox: GitSandbox) -> None:
    git_sandbox.write(BASELINE, '{"a.py": {"m": true}}')
    sha = git_sandbox.commit("corrupt")
    with pytest.raises(StateError):
        repo(git_sandbox).baseline_at(sha)


def test_diff_carries_renames_and_the_merge_base_resolves(
    git_sandbox: GitSandbox,
) -> None:
    git_sandbox.write("old.py", "x = 1\n" * 20)
    fork = git_sandbox.commit("fork")
    git_sandbox.run_git("update-ref", "refs/remotes/origin/main", fork)
    git_sandbox.run_git("mv", "old.py", "new.py")
    git_sandbox.write("other.py", "y = 2\n")
    git_sandbox.commit("rename and add")
    git = repo(git_sandbox)
    base = git.resolve(None)
    assert base == fork
    diff = git.changes_since(fork)
    assert diff.renames == {"new.py": "old.py"}
    assert diff.touched == {"new.py", "other.py"}
    assert diff.python_files() == diff.touched


def test_outside_a_repo_degrades_to_none() -> None:
    git = GitRepo(Path("/nonexistent-oo-ratchet-xyz"), BASELINE, AUDIT)
    assert git.root is None
    assert git.resolve(None) is None
    assert git.head() is None
    assert git.baseline_at("HEAD") is None


def test_new_adapters_check_a_real_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GitRepo, JsonBaselineStore, AuditFile and SourceTree wired into Check."""
    monkeypatch.chdir(tmp_path)
    fx = GitFixture(tmp_path)
    fx.write("sub/w.py", GOOD)
    fx.snapshot("sub")
    base = fx.commit("base")
    fx.write("sub/w.py", WORSE)
    fx.snapshot("sub")
    fx.commit("regress")

    def scan() -> Measurement:
        scorer = fx.scorer()
        by_file = Baseline.metrics_by_file(scorer.results)
        return Measurement(
            tuple(Score(p, m) for p, m in by_file.items()),
            frozenset(scorer.parse_errors),
        )

    ports = Ports(
        GitRepo(fx.root, BASELINE, AUDIT),
        JsonBaselineStore(fx.root / BASELINE),
        AuditFile(fx.root / AUDIT),
        SourceTree(fx.root, scan),
    )
    check = Check(oo_policy(), ports)
    verdict = check.run(base_ref=base, require_base=True)
    assert [f.kind for f in verdict.failures] == ["regression", "no-improvement"]
    assert verdict.failures[0].subjects
    assert all(x.startswith("sub/w.py: ") for x in verdict.failures[0].subjects)
