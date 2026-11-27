"""``--suggest`` output stays inert when pasted, and script targets are validated."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from oo_ratchet.design.layer_table import LayerTable
from oo_ratchet.layers.cli import main
from tests.layers_repo import LayersRepo
from tests.test_layers_suggest import PROJECT, rings, start

LS = chr(0x2028)
HOSTILE = "x\n[tool.other]\nfoo = 1"
RINGS = {"entry", "adapters", "application", "domain"}


def assert_inert(out: str) -> None:
    """The whole output parses and holds only the four-ring layers table."""
    parsed = tomllib.loads(out)
    assert set(parsed) == {"tool"}
    assert set(parsed["tool"]) == {"oo-ratchet"}
    assert set(parsed["tool"]["oo-ratchet"]) == {"layers"}
    assert set(parsed["tool"]["oo-ratchet"]["layers"]) == RINGS


class TestInertOutput:
    """No dynamic text may start an active TOML line."""

    def test_newline_in_a_module_name(self, repo: LayersRepo) -> None:
        start(repo)
        repo.write(f"src/app/{HOSTILE}.py", "import json\n")
        out = repo.run("--suggest")[1]
        assert_inert(out)
        assert "[tool.other]" in out
        assert "\\n[tool.other]" in out

    def test_carriage_return_and_unicode_separators(self, repo: LayersRepo) -> None:
        start(repo)
        for name in ("a\r[evil]", "b" + LS + "[evil]", "c\x85[evil]", "d\x7f[evil]"):
            repo.write(f"src/app/{name}.py", "import json\n")
        out = repo.run("--suggest")[1]
        assert_inert(out)
        assert "\r" not in out
        assert LS not in out

    def test_newline_in_a_script_key(self, repo: LayersRepo) -> None:
        start(repo)
        text = (
            '[project]\nname = "app"\n[project.scripts]\n'
            '"a\\n[tool.other]\\nfoo = 1" = "app.runner:main"\n'
        )
        repo.write("pyproject.toml", text)
        repo.write("src/app/runner.py", "")
        out = repo.run("--suggest")[1]
        assert_inert(out)
        assert "app.runner" in out

    def test_newline_in_the_package_name(self, tmp_path: Path) -> None:
        pkg = tmp_path / "src" / "pk\n[evil]"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "a.py").write_text("")
        (tmp_path / "pyproject.toml").write_text(PROJECT)
        out = capture(pkg)
        assert_inert(out)


def capture(pkg: Path) -> str:
    """Run ``--suggest`` and return stdout."""
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        assert main([str(pkg), "--suggest"]) == 0
    return buffer.getvalue()


class TestScriptTargets:
    """A target must be a PEP 621 object reference."""

    @pytest.mark.parametrize(
        "target", ["app.runner:", ":main", "a b:c", "app.runner:f:g", "app..x", "1x:f"]
    )
    def test_malformed_target_fails(self, repo: LayersRepo, target: str) -> None:
        start(repo)
        repo.write(
            "pyproject.toml",
            f'[project]\nname = "app"\n[project.scripts]\nrun = "{target}"\n',
        )
        code, out = repo.run("--suggest")
        assert code == 1
        assert out.startswith("FAIL:")
        assert "run" in out
        assert "\n" not in out.rstrip("\n")

    @pytest.mark.parametrize(
        "target",
        [
            "app.runner",
            "app.runner:main",
            "app.runner:Cls.meth",
            "app.runner:main [extra]",
            "app.runner [extra]",
        ],
    )
    def test_valid_target_still_marks_entry(
        self, repo: LayersRepo, target: str
    ) -> None:
        start(repo)
        repo.write(
            "pyproject.toml",
            f'[project]\nname = "app"\n[project.scripts]\nrun = "{target}"\n',
        )
        repo.write("src/app/runner.py", "")
        assert "app.runner" in rings(repo.run("--suggest")[1])["entry"]


class TestPrefixEscape:
    """A bracketed package and its children share one ring: the glob is escaped."""

    def test_glob_is_escaped_and_does_not_claim_a_sibling(
        self, repo: LayersRepo
    ) -> None:
        start(repo)
        repo.write("src/app/p[1]/__init__.py", "import json\n")
        repo.write("src/app/p[1]/a.py", "import json\n")
        repo.write("src/app/p[1]/b.py", "import json\n")
        repo.write("src/app/p1/__init__.py", "")
        repo.write("src/app/p1/mod.py", "X = 1\n")
        out = repo.run("--suggest")[1]
        adapters = rings(out)["adapters"]
        assert "app.p[[]1].*" in adapters
        config = LayerTable.from_text(PROJECT + "\n" + out, "t")
        assert config is not None
        assert config.layer("app.p[1].a") == "adapters"
        assert config.layer("app.p[1]") == "adapters"
        assert config.layer("app.p1.mod") == "domain"
