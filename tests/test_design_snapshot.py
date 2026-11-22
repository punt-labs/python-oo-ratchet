"""Real worktree cleanup with simulated slow or failed Git checkouts."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from oo_ratchet.design.shadow_snapshot import ShadowSnapshot
from oo_ratchet.oo.gitio import GitError, GitRepo
from tests.test_design_shadow import git, seed


@pytest.fixture
def repo(tmp_path: Path) -> GitRepo:
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "pkg").mkdir()
    seed(tmp_path, {"model.py": "value = 1\n"})
    return GitRepo(tmp_path)


@pytest.mark.parametrize(
    "mode",
    ["success", "timeout", "locked-timeout", "error", "early-error", "body-error"],
)
def test_checkout_timeout_and_cleanup(repo: GitRepo, mode: str) -> None:
    assert repo.root is not None
    before = git(repo.root, "worktree", "list", "--porcelain")
    run = subprocess.run
    calls: list[tuple[list[str], float]] = []
    trees: list[Path] = []

    def checkout(
        args: list[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: float,
        cwd: Path | None,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((args, timeout))
        adding = args[3:5] == ["worktree", "add"]
        if adding:
            trees.append(Path(args[-2]))
            if mode == "early-error":
                return subprocess.CompletedProcess(args, 1, "", "checkout failed")
        result = run(
            args, capture_output=capture_output, text=text, timeout=timeout, cwd=cwd
        )
        if adding and mode in {"timeout", "locked-timeout", "error"}:
            (trees[-1] / "untracked.txt").write_text("partial checkout\n")
            (trees[-1] / "pkg/model.py").unlink()
            if mode == "locked-timeout":
                run(["git", "worktree", "lock", str(trees[-1])], cwd=cwd, check=True)
            if mode == "error":
                return subprocess.CompletedProcess(args, 1, "", "checkout failed")
            raise subprocess.TimeoutExpired(args, timeout)
        return result

    with patch("oo_ratchet.oo.gitio.subprocess.run", side_effect=checkout):
        if mode == "success":
            with ShadowSnapshot(repo, "HEAD").checkout() as tree:
                assert (tree / "pkg/model.py").read_text() == "value = 1\n"
        else:
            error = ValueError if mode == "body-error" else GitError
            with pytest.raises(error), ShadowSnapshot(repo, "HEAD").checkout() as tree:
                (tree / "untracked.txt").write_text("scan interrupted\n")
                raise ValueError("scan failed")
        assert repo.resolve_ref("HEAD") is not None

    assert git(repo.root, "worktree", "list", "--porcelain") == before
    assert all(not tree.exists() for tree in trees)
    assert [timeout for args, timeout in calls if args[3:5] == ["worktree", "add"]] == [
        300
    ]
    assert all(
        timeout == 10 for args, timeout in calls if args[3:5] != ["worktree", "add"]
    )
