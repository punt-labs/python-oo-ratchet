"""Shadow verdicts through the real CLI, against measured temporary git trees."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from oo_ratchet.__main__ import main


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.org", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "README.md").write_text("fixture\n")
    git(tmp_path, "add", "README.md")
    git(tmp_path, "commit", "-qm", "anchor")
    return tmp_path


def write(repo: Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        path = repo / "pkg" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def seed(repo: Path, files: dict[str, str]) -> None:
    write(repo, files)
    if files:
        git(repo, "add", *(f"pkg/{name}" for name in files))
    git(repo, "commit", "--allow-empty", "-qm", "base")
    git(repo, "tag", "base")


def scan(repo: Path, capsys: pytest.CaptureFixture[str], *args: str) -> str:
    assert main(["design", str(repo / "pkg"), "--shadow-check", "base", *args]) == 0
    output = capsys.readouterr()
    assert not output.err
    return output.out


@pytest.mark.parametrize(
    "before,after,expected",
    [
        ("def _f(): return 1\n", "x=0\n" * 401, "would-fail: tier0"),
        ("def f(a: V,b: V): return a\n", "def f(a,b): return a\n", "would-fail: tier1"),
        ("def f(a,b): return a\n", "def f(a: V,b: V): return a\n", "good-deed: trade"),
        ("def _f(): return 1\n", "def _f():\n x=1\n return x\n", "would-fail: tier2"),
        ("def _f(a,b): return a\n", "def _f(a): return a\n", "good-deed"),
        ("def _f(): return 1\n", "def _f(): return 1\n", "neutral"),
        ("", "", "neutral"),
    ],
    ids=["tier0", "tier1", "trade", "tier2", "improve", "neutral", "empty"],
)
def test_verdict_branches(
    repo: Path,
    capsys: pytest.CaptureFixture[str],
    before: str,
    after: str,
    expected: str,
) -> None:
    seed(repo, {"model.py": before})
    write(repo, {"model.py": after})
    status = git(repo, "status", "--porcelain")
    worktrees = git(repo, "worktree", "list", "--porcelain")
    payload = json.loads(scan(repo, capsys, "--json"))
    assert payload["verdict"] == expected
    assert payload["advisory"] is True
    assert payload["base"] == git(repo, "rev-parse", "base")
    assert git(repo, "status", "--porcelain") == status
    assert git(repo, "worktree", "list", "--porcelain") == worktrees


def test_trade_is_repo_wide_and_accepts_oo_regressions(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(
        repo, {"debt.py": "def f(a,b): return a\n", "other.py": "def _f(): return 1\n"}
    )
    write(
        repo,
        {
            "debt.py": "def f(a: V,b: V): return a\n",
            "other.py": "def _f():\n x=1\n return x\n",
        },
    )
    payload = json.loads(scan(repo, capsys, "--json"))
    assert payload["verdict"] == "good-deed: trade"
    assert payload["tier1"]["removed"] == [
        {"rule": "primitive-params", "module": "pkg.debt", "symbol": "f"}
    ]
    assert payload["tier2"]["regressed"]
    assert payload["tier2"]["accepted"] == payload["tier2"]["regressed"]


@pytest.mark.parametrize("cap", [False, True])
def test_new_design_keys_cannot_be_paid_for_by_removals(
    repo: Path, capsys: pytest.CaptureFixture[str], cap: bool
) -> None:
    seed(repo, {"model.py": "def f(a,b): pass\ndef g(a,b): pass\n"})
    source = "def f(a: V,b: V): pass\ndef g(a: V,b: V): pass\ndef h(a,b): pass\n"
    write(repo, {"model.py": source + ("x=0\n" * 401 if cap else "")})
    payload = json.loads(scan(repo, capsys, "--json"))
    assert len(payload["tier1"]["removed"]) == 2
    assert len(payload["tier1"]["added"]) == 1
    assert payload["verdict"] == ("would-fail: tier0" if cap else "would-fail: tier1")
    assert payload["tier2"]["accepted"] == []


def test_oo_improvement_does_not_cancel_oo_regression(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(repo, {"model.py": "def _f(a,b): return a\n"})
    write(repo, {"model.py": "def _f(a):\n x=1\n return a\n"})
    payload = json.loads(scan(repo, capsys, "--json"))
    assert payload["tier2"]["improved"] and payload["tier2"]["regressed"]
    assert payload["verdict"] == "would-fail: tier2"


def test_removed_tier0_is_not_a_trade(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(repo, {"model.py": "import os\n"})
    write(repo, {"model.py": "import math\n"})
    config = repo / "layers.toml"
    config.write_text('[tool.oo-ratchet.layers]\ndomain=["pkg*"]\n')
    payload = json.loads(scan(repo, capsys, "--layers", str(config), "--json"))
    assert payload["tier0"]["removed"]
    assert not payload["tier1"]["removed"]
    assert payload["verdict"] == "neutral"


def test_rename_is_new_and_removed_keys(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(repo, {"old.py": "def f(a,b): return a\n"})
    (repo / "pkg/old.py").rename(repo / "pkg/new.py")
    payload = json.loads(scan(repo, capsys, "--json"))
    assert payload["verdict"] == "would-fail: tier1"
    assert payload["tier1"]["added"][0]["module"] == "pkg.new"
    assert payload["tier1"]["removed"][0]["module"] == "pkg.old"


@pytest.mark.parametrize("extra", [[], ["--json"]])
def test_repeat_output_is_byte_identical(
    repo: Path, capsys: pytest.CaptureFixture[str], extra: list[str]
) -> None:
    seed(repo, {"__init__.py": "", "sub/__init__.py": "def f(a,b): pass\n"})
    write(repo, {"sub/__init__.py": "\n\n\ndef f(a,b): pass\n"})
    first = scan(repo, capsys, *extra)
    assert scan(repo, capsys, *extra) == first
    if extra:
        payload = json.loads(first)
        assert payload["tier1"] == {"added": [], "removed": []}
    else:
        assert first.startswith("neutral (shadow; advisory)\n")
        assert (
            first.index("tier0 added")
            < first.index("tier1 added")
            < first.index("tier2 deltas")
        )


def test_divergent_ref_uses_merge_base(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(repo, {"model.py": "def _f(): return 1\n"})
    git(repo, "checkout", "-qb", "side")
    write(repo, {"model.py": "def f(a,b): pass\n"})
    git(repo, "add", "pkg/model.py")
    git(repo, "commit", "-qm", "side debt")
    git(repo, "checkout", "-q", "main")
    assert main(["design", str(repo / "pkg"), "--shadow-check", "side", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["base"] == git(repo, "rev-parse", "base")
    assert payload["verdict"] == "neutral"


def test_baseline_files_are_ignored(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(repo, {"model.py": "def _f(): return 1\n"})
    (repo / ".oo-baseline.json").write_text("not JSON")
    (repo / ".oo-audit.jsonl").write_text("also not JSON")
    assert json.loads(scan(repo, capsys, "--json"))["verdict"] == "neutral"


def test_package_initializers_have_package_module_keys(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(
        repo,
        {"__init__.py": "def f(a,b): pass\n", "sub/__init__.py": "def f(a,b): pass\n"},
    )
    write(
        repo,
        {
            "__init__.py": "\n\ndef g(a,b): pass\n",
            "sub/__init__.py": "\n\ndef g(a,b): pass\n",
        },
    )
    payload = json.loads(scan(repo, capsys, "--json"))
    assert payload["tier1"] == {
        "added": [
            {"rule": "primitive-params", "module": m, "symbol": "g"}
            for m in ("pkg", "pkg.sub")
        ],
        "removed": [
            {"rule": "primitive-params", "module": m, "symbol": "f"}
            for m in ("pkg", "pkg.sub")
        ],
    }


def test_new_source_directory_and_new_file_metrics(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(repo, {})
    write(repo, {"model.py": "def _f(): return 1\n"})
    payload = json.loads(scan(repo, capsys, "--json"))
    assert payload["verdict"] == "would-fail: tier2"
    assert any(row["status"] == "FAIL" for row in payload["tier2"]["deltas"])


@pytest.mark.parametrize("bad", ["ref", "layers", "syntax", "encoding"])
def test_input_errors_exit_two(
    repo: Path, capsys: pytest.CaptureFixture[str], bad: str
) -> None:
    seed(repo, {"model.py": "def _f(): return 1\n"})
    ref = "missing-ref" if bad == "ref" else "base"
    args = ["design", str(repo / "pkg"), "--shadow-check", ref]
    if bad == "layers":
        args.extend(["--layers", str(repo / "missing.toml")])
    if bad == "syntax":
        write(repo, {"model.py": "def broken("})
    if bad == "encoding":
        (repo / "pkg/model.py").write_bytes(b"\xff")
    assert main(args) == 2
    output = capsys.readouterr()
    assert not output.out and output.err.startswith("oo-ratchet design:")


def test_non_git_input_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["design", str(tmp_path), "--shadow-check", "HEAD"]) == 2
    assert "requires a git repository" in capsys.readouterr().err


def test_unrelated_history_is_an_input_error(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(repo, {"model.py": "def _f(): return 1\n"})
    git(repo, "checkout", "--orphan", "unrelated")
    git(repo, "commit", "-qm", "unrelated root")
    git(repo, "checkout", "-q", "main")
    assert main(["design", str(repo / "pkg"), "--shadow-check", "unrelated"]) == 2
    assert "merge base" in capsys.readouterr().err
