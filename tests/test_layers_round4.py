"""Final round: over-approximate imports, fail closed on git, atomic files."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from oo_ratchet.coupling.gitio import GitRepo
from oo_ratchet.design.layer_edges import Edge
from oo_ratchet.layers.scan import LayerScan
from tests.layers_repo import LayersRepo

DECLARED = """\
[tool.oo-ratchet.layers.kernel]
prefixes = ["kernel"]
imports = []

[tool.oo-ratchet.layers.service]
prefixes = ["service"]
imports = ["kernel"]
"""


def _edge(tmp_path: Path, files: dict[str, str]) -> bool:
    (tmp_path / "pyproject.toml").write_text(DECLARED)
    pkg = tmp_path / "src" / "app"
    pkg.mkdir(parents=True)
    for name, text in {"__init__.py": "", "service.py": "thing = 1\n", **files}.items():
        path = pkg / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return Edge("app.kernel", "app.service") in LayerScan(pkg).edges


class TestOverApproximatedImports:
    """Deliberate false positives: the gate never passes a forbidden import."""

    @pytest.mark.parametrize(
        "kernel",
        [
            'def f(x=importlib.import_module("app.service")):\n    pass\n',
            '@deco(importlib.import_module("app.service"))\ndef f():\n    pass\n',
            'class A:\n    value = importlib.import_module("app.service")\n',
            'load = lambda: importlib.import_module("app.service")\n',
            'import_module = other\nimportlib.import_module("app.service")\n',
            'loader.import_module("app.service")\n',
            'from .mine import import_module\nimport_module("app.service")\n',
        ],
    )
    def test_any_literal_import_call_is_an_edge(
        self, tmp_path: Path, kernel: str
    ) -> None:
        assert _edge(tmp_path, {"kernel.py": kernel})

    def test_wildcard_chain_reaches_the_defining_module(self, tmp_path: Path) -> None:
        files = {
            "__init__.py": "from .mid import *\n",
            "mid/__init__.py": "from ..service import *\n",
            "kernel.py": "from app import thing\n",
        }
        assert _edge(tmp_path, files)

    @pytest.mark.parametrize(
        "init",
        [
            "from .service import *\n__all__ = ['other']\n",
            "from .service import *\n__all__ = ['a'] + other.__all__\n",
            "from .service import *\ndel thing\n",
            "from .service import thing\nwith ctx() as thing:\n    pass\n",
        ],
    )
    def test_exports_are_never_removed(self, tmp_path: Path, init: str) -> None:
        files = {"__init__.py": init, "kernel.py": "from app import thing\n"}
        assert _edge(tmp_path, files)


class TestGitFailsClosed:
    """A failing git call is an error, never an absent package."""

    def test_failed_ls_files_does_not_retire_rows(
        self, repo: LayersRepo, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo.edit("kernel", "")
        repo.write(".oo-layers-baseline.json", '{"other.kernel": ["other.service"]}')
        real = GitRepo._git

        def flaky(self: GitRepo, args: list[str]) -> str | None:
            return None if args[0] == "ls-files" else real(self, args)

        monkeypatch.setattr(GitRepo, "_git", flaky)
        code, out = repo.run("--update")
        assert code == 1
        assert "FAIL" in out
        assert json.loads(repo.baseline.read_text()) == {
            "other.kernel": ["other.service"]
        }

    def test_unstaged_deletion_retires_rows(self, repo: LayersRepo) -> None:
        repo.edit("kernel", "")
        repo.write("src/other/__init__.py", "")
        repo.write(".oo-layers-baseline.json", '{"other.kernel": ["other.service"]}')
        repo.commit()
        (repo.root / "src" / "other" / "__init__.py").unlink()
        assert repo.run("--update")[0] == 0
        assert json.loads(repo.baseline.read_text()) == {}


class TestAtomicFiles:
    """Interrupted writes leave no partial audit line; modes are kept."""

    def test_a_partial_audit_write_is_rolled_back(
        self, repo: LayersRepo, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo.adopt()
        audit = repo.root / ".oo-layers-audit.jsonl"
        before = audit.read_bytes()
        repo.edit("kernel", "")
        real = os.write

        def half(fd: int, data: bytes | memoryview) -> int:
            real(fd, bytes(data)[: len(data) // 2])
            raise OSError("disk full")

        monkeypatch.setattr(os, "write", half)
        code, _ = repo.run("--update")
        assert code == 1
        assert audit.read_bytes() == before

    def test_new_baseline_gets_the_default_mode(self, repo: LayersRepo) -> None:
        repo.adopt()
        assert repo.baseline.stat().st_mode & 0o777 == 0o644

    def test_existing_baseline_mode_is_kept(self, repo: LayersRepo) -> None:
        repo.adopt()
        repo.baseline.chmod(0o664)
        repo.edit("kernel", "")
        assert repo.run("--update")[0] == 0
        assert repo.baseline.stat().st_mode & 0o777 == 0o664


def test_a_moved_package_keeps_its_base_rows(repo: LayersRepo) -> None:
    """Moving a package directory under the same import name is not an adoption."""
    repo.adopt()
    base = repo.commit_as_origin_main()
    subprocess.run(["mkdir", "lib"], cwd=repo.root, check=True)
    subprocess.run(["mv", "src/app", "lib/app"], cwd=repo.root, check=True)
    rows = {"app.kernel": ["app.service"], "app.service": ["app.cli"]}
    repo.write(".oo-layers-baseline.json", json.dumps(rows))
    repo.write("lib/app/service.py", "import app.kernel\nimport app.cli\n")
    code, out = repo.run_on(repo.root / "lib" / "app", "--check", "--base-ref", base)
    assert code == 1
    assert "did not" in out
