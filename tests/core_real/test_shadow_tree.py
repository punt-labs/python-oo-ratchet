"""The core adapter that checks a base commit out beside the work tree."""

from __future__ import annotations

from pathlib import Path

import pytest

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
    assert ShadowTree(repo).fork_point("side") == git(repo, "rev-parse", "base")


def test_unrelated_histories_have_no_fork_point(repo: Path) -> None:
    seed(repo, {"model.py": "def _f(): return 1\n"})
    git(repo, "checkout", "--orphan", "unrelated")
    git(repo, "commit", "-qm", "unrelated root")
    git(repo, "checkout", "-q", "main")
    with pytest.raises(GitError, match="no resolvable merge base"):
        ShadowTree(repo).fork_point("unrelated")


def test_unresolvable_ref_has_no_fork_point(repo: Path) -> None:
    with pytest.raises(GitError, match="no resolvable merge base"):
        ShadowTree(repo).fork_point("missing-ref")


def test_renames_since_a_base(repo: Path) -> None:
    seed(repo, {"old.py": "def f(a,b): return a\n"})
    (repo / "pkg/old.py").rename(repo / "pkg/new.py")
    git(repo, "add", "-A")
    assert ShadowTree(repo).renames("base") == {"pkg/new.py": "pkg/old.py"}


def test_root_over_rejects_a_path_outside_the_repository(repo: Path) -> None:
    with pytest.raises(GitError, match="outside"):
        ShadowTree(repo).root_over([repo.parent], "outside")
    assert ShadowTree(repo).root_over([repo / "pkg"], "outside") == repo.resolve()


def test_checkout_yields_the_base_tree_and_unregisters_it(repo: Path) -> None:
    seed(repo, {"model.py": "value = 1\n"})
    write(repo, {"model.py": "value = 2\n"})
    before = git(repo, "worktree", "list", "--porcelain")
    with ShadowTree(repo).checkout("base") as tree:
        assert (tree / "pkg/model.py").read_text() == "value = 1\n"
    assert not tree.exists()
    assert git(repo, "worktree", "list", "--porcelain") == before


def test_checkout_outside_a_repository_is_a_git_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    shadow = ShadowTree(tmp_path)
    with pytest.raises(GitError, match="requires a git repository"):
        shadow.root_over([], "--shadow-check requires a git repository")
    with (
        pytest.raises(GitError, match="requires a git repository"),
        shadow.checkout("HEAD"),
    ):
        pass
