"""Domain purity edges: package names that look like IO, respelled opens, guidance."""

from __future__ import annotations

import json

import pytest

from tests.layers_repo import LayersRepo

FLAG = "--allow-config-change"
GUIDE = "port in the application layer"


def _fixed(repo: LayersRepo, pkg: str, files: dict[str, str]) -> None:
    """Write a fixed-form package ``pkg`` with the given modules."""
    repo.write(
        "pyproject.toml",
        f'[tool.oo-ratchet.layers]\nentry = ["{pkg}.cli", "{pkg}.cli2"]\n'
        f'domain = ["{pkg}.domain", "{pkg}.domain2"]\n',
    )
    for stale in ("kernel", "service"):
        (repo.root / f"src/app/{stale}.py").unlink(missing_ok=True)
    repo.write(f"src/{pkg}/__init__.py", "")
    for name, text in files.items():
        repo.write(f"src/{pkg}/{name}.py", text)


def _run(repo: LayersRepo, pkg: str, *args: str) -> tuple[int, str]:
    return repo.run_on(repo.root / "src" / pkg, *args)


@pytest.mark.parametrize("pkg", ["rich", "mcp", "json"])
class TestPackageNamedLikeIo:
    """A package named like an IO module has internal imports, not IO edges."""

    def test_internal_import_is_not_an_io_edge(
        self, repo: LayersRepo, pkg: str
    ) -> None:
        _fixed(
            repo,
            pkg,
            {
                "cli": "",
                "cli2": "",
                "domain": f"import {pkg}.domain2\n",
                "domain2": "X = 1\n",
            },
        )
        repo.commit_as_origin_main()
        assert _run(repo, pkg, "--update")[0] == 0
        assert json.loads(repo.baseline.read_text()) == {}

    def test_flag_does_not_waive_an_entry_edge(
        self, repo: LayersRepo, pkg: str
    ) -> None:
        files = {
            "cli": "",
            "cli2": "",
            "domain2": "X = 1\n",
            "domain": f"import {pkg}.cli2\n",
        }
        _fixed(repo, pkg, files)
        repo.baseline.write_text(json.dumps({f"{pkg}.domain": [f"{pkg}.cli2"]}))
        repo.commit_as_origin_main()
        repo.write(f"src/{pkg}/domain.py", f"import {pkg}.cli2\nimport {pkg}.cli\n")
        code, out = _run(repo, pkg, "--update", FLAG)
        assert code == 1
        assert f"{pkg}.domain -> {pkg}.cli" in out


class TestDeclaredLayerNamedIo:
    """Purity edges exist only in the fixed form; a layer called io is just a layer."""

    def test_flag_does_not_waive_an_edge_into_a_layer_called_io(
        self, repo: LayersRepo
    ) -> None:
        repo.write(
            "pyproject.toml",
            '[tool.oo-ratchet.layers.core]\nprefixes = ["core"]\nimports = []\n'
            '[tool.oo-ratchet.layers.io]\nprefixes = ["io"]\nimports = []\n'
            '[tool.oo-ratchet.layers.other]\nprefixes = ["other"]\nimports = []\n',
        )
        for name in ("kernel", "service", "cli"):
            (repo.root / f"src/app/{name}.py").unlink()
        repo.write("src/app/core.py", "import app.other\n")
        repo.write("src/app/io.py", "")
        repo.write("src/app/other.py", "")
        repo.baseline.write_text(json.dumps({"app.core": ["app.other"]}))
        repo.commit_as_origin_main()
        repo.write("src/app/core.py", "import app.other\nimport app.io\n")
        code, out = repo.run("--update", FLAG)
        assert code == 1
        assert "app.core -> app.io" in out


class TestRespelledOpen:
    """Every spelling of the builtin open is a ``builtins.open`` edge."""

    @pytest.mark.parametrize(
        "body",
        [
            "import builtins\n\n\ndef f():\n    return builtins.open('x')\n",
            "import builtins as b\n\n\ndef f():\n    return b.open('x')\n",
            "from builtins import open\n",
            "from builtins import open as o\n",
        ],
    )
    def test_spelling_is_an_edge(self, repo: LayersRepo, body: str) -> None:
        _fixed(repo, "app", {"cli": "", "cli2": "", "domain": "X = 1\n", "domain2": ""})
        repo.commit_as_origin_main()
        assert _run(repo, "app", "--update")[0] == 0
        repo.write("src/app/domain.py", body)
        code, out = _run(repo, "app", "--check")
        assert code == 1
        assert "app.domain -> builtins.open" in out


class TestTypeOnlyDynamicImport:
    """A literal dynamic import under TYPE_CHECKING is not an edge."""

    def test_type_checking_dynamic_import_is_ignored(self, repo: LayersRepo) -> None:
        body = (
            "import importlib\nfrom typing import TYPE_CHECKING\n\n"
            "if TYPE_CHECKING:\n    importlib.import_module('subprocess')\n"
        )
        _fixed(repo, "app", {"cli": "", "cli2": "", "domain": body, "domain2": ""})
        repo.commit_as_origin_main()
        assert _run(repo, "app", "--update")[0] == 0
        assert json.loads(repo.baseline.read_text()) == {}


class TestGuidance:
    """An io edge's refusal and check output name the way out; others do not."""

    def _files(self, domain: str) -> dict[str, str]:
        return {"cli": "", "cli2": "", "domain": domain, "domain2": ""}

    def test_check_names_the_way_out_for_an_io_edge(self, repo: LayersRepo) -> None:
        _fixed(repo, "app", self._files("X = 1\n"))
        repo.commit_as_origin_main()
        assert _run(repo, "app", "--update")[0] == 0
        repo.write("src/app/domain.py", "import subprocess\n")
        code, out = _run(repo, "app", "--check")
        assert code == 1
        assert GUIDE in out
        assert "--allow-config-change" in out

    def test_update_refusal_names_the_way_out_for_an_io_edge(
        self, repo: LayersRepo
    ) -> None:
        _fixed(repo, "app", self._files("import app.cli2\n"))
        repo.baseline.write_text(json.dumps({"app.domain": ["app.cli2"]}))
        repo.commit_as_origin_main()
        repo.write("src/app/domain.py", "import app.cli2\nimport subprocess\n")
        code, out = _run(repo, "app", "--update")
        assert code == 1
        assert GUIDE in out

    def test_non_io_edge_has_no_guidance(self, repo: LayersRepo) -> None:
        _fixed(repo, "app", self._files("import app.cli2\n"))
        code, out = _run(repo, "app", "--check")
        assert code == 1
        assert "app.domain -> app.cli2" in out
        assert GUIDE not in out
