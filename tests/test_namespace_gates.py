"""Exercise all namespace gates against real Git baselines and file moves."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oo_ratchet.__main__ import main
from oo_ratchet.core.adapters.gitrepo import GitRepo
from oo_ratchet.core.adapters.tallyrepo import TallyRepo
from oo_ratchet.core.adapters.treeviews import BaseTree, WorkingTree
from oo_ratchet.core.domain.tallies import Tally
from oo_ratchet.coupling.cli import CouplingOptions
from oo_ratchet.source_set import Source, SourceSet
from oo_ratchet.suppression.scanner import Scanner
from tests.conftest import GitSandbox
from tests.test_namespace_sources import CONFIG, HEADER


def rescan(root: Path, ref: str, source: Source) -> Tally | None:
    """Count ``source`` as it stood at ``ref`` through the core's history adapter."""
    git = GitRepo(root, ".suppression-baseline.json", ".suppression-audit.jsonl")

    def scan(target: Source, project: Path) -> Tally:
        report = Scanner(target, project).report
        return Tally(report.by_category, report.by_file)

    return TallyRepo(git, source, root, scan, ".suppression-relax.json").tally_at(ref)


@pytest.fixture
def workspace(git_sandbox: GitSandbox, monkeypatch: pytest.MonkeyPatch) -> GitSandbox:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    repo = git_sandbox
    monkeypatch.chdir(repo.root)
    repo.write("pyproject.toml", CONFIG)
    repo.write("src/app/__init__.py", HEADER)
    repo.write("src/app/a/__init__.py", HEADER)
    repo.write("src/app/b/__init__.py", HEADER)
    repo.write(
        "src/app/a/core.py",
        HEADER + 'class Alpha:\n    def run(self) -> str:\n        return "a"\n',
    )
    repo.write(
        "src/app/b/core.py",
        HEADER + "from app.a.core import Alpha\nclass Beta:\n"
        "    def run(self) -> str:\n        return Alpha().run()\n",
    )
    return repo


def move(repo: GitSandbox) -> list[str]:
    repo.run_git("update-ref", "refs/remotes/origin/main", "HEAD")
    roots = []
    for name in ("a", "b"):
        root = repo.root / f"packages/{name}/src/app"
        root.mkdir(parents=True)
        repo.run_git("mv", f"src/app/{name}", str(root / name))
        roots.append(str(root))
    repo.run_git("mv", "src/app/__init__.py", str(Path(roots[0]) / "__init__.py"))
    return roots


@pytest.mark.parametrize("gate", ["oo", "coupling", "suppressions", "layers"])
def test_update_check_and_require_base_follow_physical_renames(
    workspace: GitSandbox, capsys: pytest.CaptureFixture[str], gate: str
) -> None:
    repo = workspace
    assert main([gate, "src/app", "--update"]) == 0
    capsys.readouterr()
    base = repo.commit("baseline")
    roots = move(repo)
    code = main(
        [
            gate,
            "--namespace",
            "app",
            *roots,
            "--check",
            "--base-ref",
            base,
            "--require-base",
        ]
    )
    report = capsys.readouterr().out
    assert "regressed" not in report.lower()
    assert "cannot" not in report.lower()
    assert code == (1 if gate == "oo" else 0), report
    if gate == "oo":
        assert "(all metrics unchanged)" in report
        assert "FAIL: no metric improved" in report
    assert (
        main(
            [
                gate,
                "--namespace",
                "app",
                *roots,
                "--check",
                "--base-ref",
                "missing-ref",
                "--require-base",
            ]
        )
        == 1
    )
    assert "--require-base" in capsys.readouterr().out
    assert main([gate, "--namespace", "app", *roots, "--update"]) == 0


def test_shadow_joins_roots_and_pairs_renamed_metrics(
    workspace: GitSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = workspace
    base = repo.commit("source")
    roots = move(repo)
    assert (
        main(["design", "--namespace", "app", *roots, "--shadow-check", base, "--json"])
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["tier0"] == {"added": [], "removed": []}
    assert payload["tier1"] == {"added": [], "removed": []}


def test_namespace_coupling_cap_matches_physical_key(
    workspace: GitSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = workspace
    roots = move_after_commit(repo)
    path = "packages/b/src/app/b/core.py"
    repo.write(
        "pyproject.toml",
        CONFIG + "\n[tool.oo-ratchet.coupling.caps]\n"
        f'"{path}" = {{ efferent_coupling = 0 }}\n',
    )
    assert main(["coupling", "--namespace", "app", *roots, "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["grades"]["efferent_coupling"] == "FAIL"


def move_after_commit(repo: GitSandbox) -> list[str]:
    repo.commit("source")
    return move(repo)


def test_namespace_waiver_uses_repo_relative_file_key(
    workspace: GitSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = workspace
    assert main(["suppressions", "src/app", "--update"]) == 0
    capsys.readouterr()
    base = repo.commit("baseline")
    roots = move(repo)
    path = "packages/a/src/app/a/core.py"
    file = repo.root / path
    file.write_text(file.read_text() + "value = 1  # noqa: F841\n")
    args = ["suppressions", "--namespace", "app", *roots]
    assert (
        main(
            [
                *args,
                "--relax",
                path,
                "--justify",
                "namespace fixture",
                "--base-ref",
                base,
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main([*args, "--check", "--base-ref", base, "--require-base"]) == 0
    assert "waived" in capsys.readouterr().out


def test_configured_layers_catch_new_cross_root_violation(
    workspace: GitSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = workspace
    assert main(["layers", "src/app", "--update"]) == 0
    capsys.readouterr()
    base = repo.commit("baseline")
    roots = move(repo)
    file = repo.root / "packages/a/src/app/a/core.py"
    file.write_text(file.read_text() + "from app.b.core import Beta\n")
    assert (
        main(
            [
                "layers",
                "--namespace",
                "app",
                *roots,
                "--check",
                "--base-ref",
                base,
                "--require-base",
            ]
        )
        == 1
    )
    assert "app.a.core -> app.b.core" in capsys.readouterr().out


def test_updating_another_package_keeps_namespace_baseline(
    workspace: GitSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = workspace
    roots = move_after_commit(repo)
    (Path(roots[0]) / "__init__.py").unlink()
    repo.write("packages/a/src/app/a/core.py", HEADER + "import app.b.core\n")
    assert main(["layers", "--namespace", "app", *roots, "--update"]) == 0
    baseline = repo.root / ".oo-layers-baseline.json"
    before = json.loads(baseline.read_text())
    assert before["app.a.core"] == ["app.b.core"]
    repo.write("src/other/__init__.py", HEADER)
    repo.write("src/other/a/core.py", HEADER)
    repo.write("src/other/b/core.py", HEADER)
    assert main(["layers", "src/other", "--update"]) == 0
    assert json.loads(baseline.read_text()) == before, capsys.readouterr().out


def test_moved_namespace_still_checks_base_layer_prefixes(
    workspace: GitSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = workspace
    (repo.root / "src/app/__init__.py").unlink()
    repo.write("src/app/b/core.py", HEADER)
    assert main(["layers", "--namespace", "app", "src/app", "--update"]) == 0
    base = repo.commit("namespace baseline")
    destination = repo.root / "packages/member/src"
    destination.mkdir(parents=True)
    repo.run_git("mv", "src/app", str(destination / "app"))
    repo.write("packages/member/src/app/a/core.py", HEADER + "import app.b.core\n")
    repo.write(
        "pyproject.toml",
        '[tool.oo-ratchet.layers.a]\nprefixes = ["a", "b"]\nimports = []\n',
    )
    code = main(
        [
            "layers",
            "--namespace",
            "app",
            str(destination / "app"),
            "--check",
            "--base-ref",
            base,
            "--require-base",
        ]
    )
    report = capsys.readouterr().out
    assert code == 1, report
    assert "app.a.core -> app.b.core" in report


def test_deleted_configured_portion_stays_in_base_suppressions(
    workspace: GitSandbox,
) -> None:
    repo = workspace
    repo.write(
        "pyproject.toml",
        '[tool.oo-ratchet]\nnamespace = "app"\n'
        'roots = ["packages/*/src/app"]\n' + CONFIG,
    )
    repo.write("packages/kept/src/app/a.py", HEADER)
    deleted = "packages/deleted/src/app/b.py"
    repo.write(deleted, HEADER + "value = 1  # noqa: F841\n")
    base = repo.commit("two configured portions")
    repo.run_git("rm", "-r", "packages/deleted")
    before = rescan(repo.root, base, CouplingOptions.parse([]).src)
    assert before is not None
    assert before.total == 1
    assert deleted in before.by_file


def test_shadow_preserves_nested_project_layer_configuration(
    workspace: GitSandbox,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = workspace
    repo.write("pyproject.toml", "")
    repo.write("nested/pyproject.toml", CONFIG)
    repo.write("nested/src/app/a.py", HEADER + "import app.b\n")
    repo.write("nested/src/app/b.py", HEADER)
    base = repo.commit("nested project")
    monkeypatch.chdir(repo.root / "nested")
    assert (
        main(
            [
                "design",
                "--namespace",
                "app",
                "src/app",
                "--shadow-check",
                base,
                "--json",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["tier0"] == {"added": [], "removed": []}


def test_renames_do_not_move_literal_ignore_pattern_counts(
    workspace: GitSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = workspace
    repo.write(
        "pyproject.toml",
        CONFIG + "\n[tool.ruff.lint.per-file-ignores]\n"
        '"src/app/a/core.py" = ["F401"]\n',
    )
    assert main(["suppressions", "src/app", "--update"]) == 0
    base = repo.commit("literal per-file ignore")
    roots = move(repo)
    path = "packages/a/src/app/a/core.py"
    file = repo.root / path
    file.write_text(file.read_text() + "value = 1  # noqa: F841\n")
    args = ["suppressions", "--namespace", "app", *roots]
    code = main(
        [*args, "--relax", path, "--justify", "new suppression", "--base-ref", base]
    )
    assert code == 0, capsys.readouterr().out
    assert main([*args, "--check", "--base-ref", base, "--require-base"]) == 0


def test_equivalent_source_root_spellings_are_deduplicated(
    workspace: GitSandbox,
) -> None:
    options = CouplingOptions.parse(["--namespace", "app", "src/app", "src/../src/app"])
    assert isinstance(options.src, SourceSet)
    assert options.src.roots == ((workspace.root / "src/app").resolve(),)


def test_namespace_history_does_not_export_unselected_symlinks(
    workspace: GitSandbox,
) -> None:
    repo = workspace
    (repo.root / "outside-link").symlink_to(repo.root.parent / "outside")
    base = repo.commit("unrelated symlink")
    legacy = rescan(repo.root, base, Path("src/app"))
    assert legacy is not None
    before = rescan(
        repo.root, base, CouplingOptions.parse(["--namespace", "app", "src/app"]).src
    )
    assert before is not None
    assert before.total == legacy.total


def test_export_ignore_is_already_honored_by_legacy_history(
    workspace: GitSandbox,
) -> None:
    repo = workspace
    repo.write(".gitattributes", "src/app/a/core.py export-ignore\n")
    repo.write("src/app/a/core.py", HEADER + "value = 1  # noqa: F841\n")
    base = repo.commit("archive exclusion")
    for source in (
        Path("src/app"),
        CouplingOptions.parse(["--namespace", "app", "src/app"]).src,
    ):
        before = rescan(repo.root, base, source)
        assert before is not None
        assert before.total == 0


def test_namespace_history_returns_none_for_an_absent_portion(
    workspace: GitSandbox,
) -> None:
    base = workspace.commit("original portions")
    workspace.write("packages/new/src/app/new.py", HEADER)
    source = CouplingOptions.parse(["--namespace", "app", "packages/new/src/app"]).src
    assert rescan(workspace.root, base, source) is None


def test_namespace_history_surfaces_directory_listing_failure(
    workspace: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = workspace.commit("original portions")
    original = GitRepo._git

    def fail_listing(repo: GitRepo, args: list[str]) -> str | None:
        return None if args[0] == "ls-tree" else original(repo, args)

    monkeypatch.setattr(GitRepo, "_git", fail_listing)
    source = CouplingOptions.parse(["--namespace", "app", "src/app"]).src
    with pytest.raises(OSError, match="git ls-tree"):
        rescan(workspace.root, base, source)


def test_nested_namespace_history_keeps_repository_ruff_ignores(
    workspace: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = workspace
    repo.write(
        "pyproject.toml",
        '[tool.ruff.lint.per-file-ignores]\n"nested/src/app/*.py" = ["F401"]\n',
    )
    repo.write("nested/pyproject.toml", CONFIG)
    repo.write("nested/src/app/core.py", HEADER)
    base = repo.commit("nested namespace with root Ruff configuration")
    monkeypatch.chdir(repo.root / "nested")
    source = CouplingOptions.parse(["--namespace", "app", "src/app"]).src
    current = Scanner(source, repo.root).report
    before = rescan(repo.root, base, source)
    assert before is not None
    assert before.total == current.total == 1


def test_historical_root_globs_ignore_deleted_namesakes(
    workspace: GitSandbox,
) -> None:
    repo = workspace
    repo.write(
        "pyproject.toml",
        '[tool.oo-ratchet]\nnamespace = "app"\nroots = ["portions/*"]\n' + CONFIG,
    )
    repo.write("portions/app/core.py", HEADER)
    repo.write("portions/other/__init__.py", HEADER)
    base = repo.commit("unrelated glob match")
    repo.run_git("rm", "-r", "portions/other")
    before = rescan(repo.root, base, CouplingOptions.parse([]).src)
    assert before is not None
    assert before.total == 0


def test_historical_root_globs_keep_resolved_symlink_portions(
    workspace: GitSandbox,
) -> None:
    repo = workspace
    repo.write(
        "pyproject.toml",
        '[tool.oo-ratchet]\nnamespace = "app"\nroots = ["members/*"]\n' + CONFIG,
    )
    repo.write("actual/app/core.py", HEADER + "value = 1  # noqa: F841\n")
    (repo.root / "members").mkdir()
    (repo.root / "members/app").symlink_to("../actual/app", target_is_directory=True)
    base = repo.commit("symlink-selected namespace")
    before = rescan(repo.root, base, CouplingOptions.parse([]).src)
    assert before is not None
    assert before.total == 1


@pytest.mark.parametrize("kind", ["base", "working"])
def test_namespace_namesakes_below_regular_ancestors_are_not_top_level(
    workspace: GitSandbox,
    kind: str,
) -> None:
    repo = workspace
    repo.commit("original top-level package")
    repo.run_git("rm", "-r", "src/app")
    repo.write("src/outer/__init__.py", HEADER)
    repo.write("src/outer/nested/app/core.py", HEADER)
    base = repo.commit("only a nested namespace namesake")
    found = (
        BaseTree(base, repo.root).package_at("app")
        if kind == "base"
        else WorkingTree(repo.root).has_package("app")
    )
    assert not found


def test_namespace_history_does_not_confuse_config_probe_failure_with_absence(
    workspace: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = workspace
    repo.write(
        "pyproject.toml",
        CONFIG + '\n[tool.ruff.lint.per-file-ignores]\n"src/app/*.py" = ["F401"]\n',
    )
    base = repo.commit("configuration present")
    original = GitRepo._git

    def fail_probe(git: GitRepo, args: list[str]) -> str | None:
        return None if args[0] == "cat-file" else original(git, args)

    monkeypatch.setattr(GitRepo, "_git", fail_probe)
    source = CouplingOptions.parse(["--namespace", "app", "src/app"]).src
    before = rescan(repo.root, base, source)
    assert before is not None
    assert before.total == 1


def test_namespace_history_accepts_missing_configuration(
    workspace: GitSandbox,
) -> None:
    (workspace.root / "pyproject.toml").unlink()
    base = workspace.commit("namespace without configuration")
    source = CouplingOptions.parse(["--namespace", "app", "src/app"]).src
    before = rescan(workspace.root, base, source)
    assert before is not None
    assert before.total == 0


def test_historical_namespace_roots_cannot_escape_the_checkout(
    workspace: GitSandbox,
) -> None:
    repo = workspace
    (repo.root / "historical/src").mkdir(parents=True)
    (repo.root / "historical/src/app").symlink_to(
        repo.root / "src/app", target_is_directory=True
    )
    source = SourceSet.from_roots((repo.root / "src/app",), "app")
    with pytest.raises(ValueError, match="historical namespace root escapes checkout"):
        source.at_base(repo.root, repo.root / "historical", {})
