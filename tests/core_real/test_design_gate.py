"""The design gate on the shared core, pinned against the previous gate.

Each scenario builds a real repository and runs ``oo_ratchet.design.cli.main``.
``design_golden.json`` holds the exit code, stdout and stderr the per-gate
implementation produced for every scenario, recorded before its git code was
deleted. Regenerate only with ``UPDATE_DESIGN_GOLDEN=1`` on a trusted tree.
Commit SHAs and the temporary directory are masked.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from oo_ratchet.design.cli import main
from tests.test_design_shadow import git, seed, write

pytestmark = pytest.mark.slow

GOLDEN = Path(__file__).with_name("design_golden.json")
SHA = re.compile(r"\b[0-9a-f]{40}\b")
DOMAIN = '[tool.oo-ratchet.layers]\ndomain=["pkg*"]\n'
BRANCHY = "def _f(a):\n if a:\n  return a\n return 0\n"
FLAT = "def _f(a): return a\n"
Build = Callable[[Path], list[str]]


def mask(text: str, root: Path) -> str:
    return SHA.sub("<SHA>", text.replace(str(root), "<ROOT>"))


def side_branch(repo: Path) -> list[str]:
    seed(repo, {"model.py": "def _f(): return 1\n"})
    git(repo, "checkout", "-qb", "side")
    write(repo, {"model.py": "def f(a,b): pass\n"})
    git(repo, "add", "pkg/model.py")
    git(repo, "commit", "-qm", "side debt")
    git(repo, "checkout", "-q", "main")
    return ["--shadow-check", "side"]


def unrelated(repo: Path) -> list[str]:
    seed(repo, {"model.py": "def _f(): return 1\n"})
    git(repo, "checkout", "--orphan", "unrelated")
    git(repo, "commit", "-qm", "unrelated root")
    git(repo, "checkout", "-q", "main")
    return ["--shadow-check", "unrelated"]


def renamed(repo: Path) -> list[str]:
    seed(repo, {"old.py": "def f(a,b): return a\n"})
    (repo / "pkg/old.py").rename(repo / "pkg/new.py")
    return ["--shadow-check", "base"]


def shadow(before: str, after: str, *extra: str) -> Build:
    def build(repo: Path) -> list[str]:
        seed(repo, {"model.py": before})
        write(repo, {"model.py": after})
        flags = ["--shadow-check", "base"]
        if "--layers" in extra:
            (repo / "layers.toml").write_text(DOMAIN)
            flags += ["--layers", str(repo / "layers.toml")]
        return flags + [e for e in extra if e != "--layers"]

    return build


def broken(kind: str) -> Build:
    def build(repo: Path) -> list[str]:
        seed(repo, {"model.py": "def _f(): return 1\n"})
        if kind == "syntax":
            write(repo, {"model.py": "def broken("})
        if kind == "encoding":
            (repo / "pkg/model.py").write_bytes(b"\xff")
        if kind == "layers":
            return ["--shadow-check", "base", "--layers", str(repo / "missing.toml")]
        return ["--shadow-check", "missing-ref" if kind == "ref" else "base"]

    return build


def plain(repo: Path) -> list[str]:
    seed(repo, {"model.py": "import os\ndef f(a,b): pass\n"})
    return []


SCENARIOS: dict[str, Build] = {
    "tier0-size-cap": shadow("def _f(): return 1\n", "x=0\n" * 401),
    "tier0-domain-io": shadow("import math\n", "import os\n", "--layers"),
    "tier0-removed-neutral": shadow("import os\n", "import math\n", "--layers"),
    "tier1-added": shadow("def f(a: V,b: V): return a\n", "def f(a,b): return a\n"),
    "tier1-trade": shadow("def f(a,b): return a\n", "def f(a: V,b: V): return a\n"),
    "tier2-regression": shadow(FLAT, BRANCHY),
    "improvement": shadow(BRANCHY, FLAT),
    "unchanged": shadow(FLAT, FLAT),
    "unchanged-json": shadow(FLAT, FLAT, "--json"),
    "regression-json": shadow(FLAT, BRANCHY, "--json"),
    "empty": shadow("", ""),
    "rename": renamed,
    "divergent-ref": side_branch,
    "missing-ref": broken("ref"),
    "bad-layers": broken("layers"),
    "syntax-error": broken("syntax"),
    "encoding-error": broken("encoding"),
    "unrelated-history": unrelated,
    "no-shadow-report": plain,
}


def run_gate(
    root: Path, argv: list[str], capsys: pytest.CaptureFixture[str]
) -> dict[str, object]:
    capsys.readouterr()
    code = main([str(root / "pkg"), *argv])
    seen = capsys.readouterr()
    return {"code": code, "out": mask(seen.out, root), "err": mask(seen.err, root)}


def test_scenarios_match_the_recorded_gate(
    tmp_path_factory: pytest.TempPathFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: dict[str, dict[str, object]] = {}
    for name, build in SCENARIOS.items():
        root = tmp_path_factory.mktemp(name.replace("-", "_"))
        git(root, "init", "-q", "-b", "main")
        (root / "pkg").mkdir()
        (root / "README.md").write_text("fixture\n")
        git(root, "add", "README.md")
        git(root, "commit", "-qm", "anchor")
        argv = build(root)
        before = git(root, "worktree", "list", "--porcelain")
        seen[name] = run_gate(root, argv, capsys)
        assert git(root, "worktree", "list", "--porcelain") == before, name
    if os.environ.get("UPDATE_DESIGN_GOLDEN") == "1":
        GOLDEN.write_text(json.dumps(seen, indent=1, sort_keys=True) + "\n")
    assert seen == json.loads(GOLDEN.read_text())


def test_not_a_directory_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(tmp_path / "nowhere")]) == 2
    assert "is not a directory" in capsys.readouterr().err
