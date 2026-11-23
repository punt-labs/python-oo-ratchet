"""Exercise all namespace gates against real Git baselines and file moves."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oo_ratchet.__main__ import main
from tests.conftest import GitSandbox
from tests.test_namespace_sources import CONFIG, HEADER


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
    if gate != "oo":
        assert code == 0, report
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
