"""The core adapter that checks a base commit out beside the work tree."""

from __future__ import annotations

from pathlib import Path

import pytest

from oo_ratchet.core.adapters.gitrepo import GitRepo
from oo_ratchet.core.adapters.shadowtree import ShadowTree
from oo_ratchet.core.domain.errors import GitError
from tests.test_design_shadow import git, seed, write

pytestmark = pytest.mark.slow


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "README.md").write_text("fixture\n")
    git(tmp_path, "add", "README.md")
    git(tmp_path, "commit", "-qm", "anchor")
    return tmp_path


def test_merge_base_resolves_a_divergent_ref(repo: Path) -> None:
    seed(repo, {"model.py": "def _f(): return 1\n"})
    git(repo, "checkout", "-qb", "side")
    write(repo, {"model.py": "def f(a,b): pass\n"})
    git(repo, "add", "pkg/model.py")
    git(repo, "commit", "-qm", "side debt")
    git(repo, "checkout", "-q", "main")
    assert GitRepo.stateless(repo).merge_base("side", "HEAD") == git(
        repo, "rev-parse", "base"
    )


def test_merge_base_is_none_for_unrelated_histories(repo: Path) -> None:
    seed(repo, {"model.py": "def _f(): return 1\n"})
    git(repo, "checkout", "--orphan", "unrelated")
    git(repo, "commit", "-qm", "unrelated root")
    git(repo, "checkout", "-q", "main")
    assert GitRepo.stateless(repo).merge_base("unrelated", "HEAD") is None


def test_checkout_yields_the_base_tree_and_unregisters_it(repo: Path) -> None:
    seed(repo, {"model.py": "value = 1\n"})
    write(repo, {"model.py": "value = 2\n"})
    before = git(repo, "worktree", "list", "--porcelain")
    with ShadowTree(GitRepo.stateless(repo), "base").checkout() as tree:
        assert (tree / "pkg/model.py").read_text() == "value = 1\n"
    assert not tree.exists()
    assert git(repo, "worktree", "list", "--porcelain") == before


def test_checkout_outside_a_repository_is_a_git_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    shadow = ShadowTree(GitRepo.stateless(tmp_path), "HEAD")
    with pytest.raises(GitError, match="requires a git repository"), shadow.checkout():
        pass
