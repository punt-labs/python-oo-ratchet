"""``--suggest`` output stays inert when pasted, and script targets are validated."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from oo_ratchet.design.layer_table import LayerTable
from oo_ratchet.layers.cli import main
from oo_ratchet.layers.suggest_text import SafeText
from tests.layers_repo import LayersRepo
from tests.test_layers_suggest import (
    MARK_ADAPTERS,
    MARK_DOMAIN,
    PROJECT,
    rings,
    start,
)

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
            repo.write(f"src/app/{name}.py", MARK_ADAPTERS)
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
        repo.write("src/app/p[1]/__init__.py", MARK_ADAPTERS)
        repo.write("src/app/p[1]/a.py", MARK_ADAPTERS)
        repo.write("src/app/p[1]/b.py", MARK_ADAPTERS)
        repo.write("src/app/p1/__init__.py", MARK_DOMAIN)
        repo.write("src/app/p1/mod.py", MARK_DOMAIN)
        out = repo.run("--suggest")[1]
        adapters = rings(out)["adapters"]
        assert "app.p[[]1].*" in adapters
        config = LayerTable.from_text(PROJECT + "\n" + out, "t")
        assert config is not None
        assert config.layer("app.p[1].a") == "adapters"
        assert config.layer("app.p[1]") == "adapters"
        assert config.layer("app.p1.mod") == "domain"


class TestEntryPointSyntax:
    """Whitespace around the colon is fine; extras are PEP 508 names."""

    @staticmethod
    def write(repo: LayersRepo, target: str) -> None:
        start(repo)
        text = f'[project]\nname = "app"\n[project.scripts]\nrun = "{target}"\n'
        repo.write("pyproject.toml", text)
        repo.write("src/app/runner.py", "")

    @pytest.mark.parametrize(
        "target",
        [
            "app.runner : main",
            "app.runner :main",
            "app.runner: main",
            "app.runner:main [a, b]",
            "app.runner:main [ a ]",
            "app.runner [a]",
            "app.runner []",
            "app.runner [ ]",
            "app.runner:main []",
            "app.runner:main [extra]",
            "app.runner:main [a.b-c_d]",
        ],
    )
    def test_valid(self, repo: LayersRepo, target: str) -> None:
        self.write(repo, target)
        code, out = repo.run("--suggest")
        assert code == 0, out
        assert "app.runner" in rings(out)["entry"]

    @pytest.mark.parametrize(
        "target",
        [
            "app.runner [!!!]",
            "app.runner [!!!",
            "app.runner [,]",
            "app.runner [a,]",
            "app.runner [,a]",
            "app.runner [a b]",
            "app.runner:main [a,,b]",
            "app.runner [-a]",
            "app.runner:",
            ":main",
            "app.runner:f:g",
            "app..x",
            "1x:f",
        ],
    )
    def test_malformed(self, repo: LayersRepo, target: str) -> None:
        self.write(repo, target)
        code, out = repo.run("--suggest")
        assert code == 1
        assert out.startswith("FAIL:")
        assert "run" in out


class TestNonBmpNames:
    """The table is valid TOML for any valid module name."""

    @pytest.mark.parametrize("name", ["\U00010400", "é", "a\U00010400b"])
    def test_round_trip(self, repo: LayersRepo, name: str) -> None:
        start(repo)
        for other in ("kernel", "service", "cli"):
            repo.edit(other, MARK_DOMAIN)
        repo.write(f"src/app/{name}.py", MARK_ADAPTERS)
        out = repo.run("--suggest")[1]
        assert_inert(out)
        layers = tomllib.loads(out)["tool"]["oo-ratchet"]["layers"]
        assert f"app.{name}" in layers["adapters"]
        repo.write("pyproject.toml", PROJECT + "\n" + out)
        code, text = repo.run("--json")
        assert code == 0
        data = json.loads(text)
        assert data["unassigned"] == []
        assert data["violations"] == []

    def test_controls_and_quotes_still_escaped(self) -> None:
        text = 'a"b\\c\x7f' + LS + "\x85\n\U00010400"
        quoted = SafeText.quoted(text)
        assert tomllib.loads(f"k = {quoted}")["k"] == text


class TestRootException:
    """The header names the root as an exception to the ring rules."""

    def test_header_names_the_exception(self, repo: LayersRepo) -> None:
        start(repo)
        out = repo.run("--suggest")[1]
        assert "The package root goes in entry" in out
        assert "non-entry module imports it" in out
        assert "relative import above the package" in out

    def test_root_with_an_unresolvable_relative_import_is_unclassified(
        self, repo: LayersRepo
    ) -> None:
        start(repo)
        repo.write("src/app/__init__.py", "from .. import x\n")
        out = repo.run("--suggest")[1]
        assert "app" not in rings(out)["entry"]
        assert "#   app: unclassified (unresolvable relative import" in out
