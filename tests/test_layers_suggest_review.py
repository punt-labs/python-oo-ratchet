"""``layers --suggest`` must agree with the gate: no table that fails on itself."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from oo_ratchet.core.domain.layer_table import LayerTable
from oo_ratchet.layers.cli import main
from tests.conftest import GitSandbox
from tests.layers_repo import LayersRepo
from tests.test_layers_suggest import (
    MARK_ADAPTERS,
    MARK_DOMAIN,
    PROJECT,
    PROTOCOL,
    rings,
    start,
)


def roundtrip(repo: LayersRepo) -> tuple[str, dict[str, object]]:
    """Write the suggestion into pyproject; return it and the gate's JSON."""
    out = repo.run("--suggest")[1]
    repo.write("pyproject.toml", PROJECT + "\n" + out)
    code, text = repo.run("--json")
    assert code == 0, text
    return out, json.loads(text)


def none_nearest(_src: object) -> None:
    """Stand in for ``LayerTable.nearest`` when no pyproject exists."""
    return


def layered(repo: LayersRepo) -> None:
    """The reviewers' repro, with declared rings: ports, model, db, cli, mid, user."""
    start(repo)
    repo.write("src/app/ports.py", MARK_DOMAIN + PROTOCOL)
    repo.write("src/app/model.py", MARK_DOMAIN + "from app.ports import Store\n")
    repo.write(
        "src/app/db.py",
        MARK_ADAPTERS + "import subprocess\nimport app.ports\nimport app.model\n",
    )
    repo.write("src/app/runner.py", "import argparse\n")
    repo.write("src/app/mid.py", MARK_DOMAIN + "from app import db\n")
    repo.write("src/app/user.py", MARK_DOMAIN + "from app import mid\n")


class TestNoSelfViolations:
    """A module is placed only where the gate would accept its imports."""

    def test_repro_package_has_no_violations(self, repo: LayersRepo) -> None:
        layered(repo)
        out, data = roundtrip(repo)
        assert data["violations"] == []
        table = rings(out)
        placed = {m for ring in table.values() for m in ring}
        assert "app.user" not in placed
        assert "app.model" in rings(out)["domain"]
        assert "CONFLICT" in out

    def test_importers_of_an_adapter_conflict_with_the_chain(
        self, repo: LayersRepo
    ) -> None:
        layered(repo)
        out = repo.run("--suggest")[1]
        assert "#   app.mid: CONFLICT" in out
        assert "app.user -> app.mid -> app.db -> json" in out

    def test_second_package_has_no_violations(self, repo: LayersRepo) -> None:
        start(repo)
        repo.write("src/app/core/__init__.py", "")
        repo.write("src/app/core/rules.py", "X = 1\n")
        repo.write("src/app/core/calc.py", "from app.core import rules\n")
        repo.write("src/app/ports.py", MARK_DOMAIN + PROTOCOL)
        repo.write(
            "src/app/store.py",
            MARK_ADAPTERS + "import sqlite3\nfrom app.ports import Store\n",
        )
        repo.write("src/app/helper.py", "import app.store\n")
        repo.write("src/app/top.py", "import typer\nimport app.helper\n")
        repo.write(
            "src/app/svc.py",
            '__ring__ = "application"\nimport app.ports\nimport app.core.calc\n',
        )
        out, data = roundtrip(repo)
        assert data["violations"] == []
        assert "app.core.calc" in out

    def test_adapter_importing_an_entry_module_is_a_conflict(
        self, repo: LayersRepo
    ) -> None:
        start(repo)
        repo.write("src/app/top.py", "import argparse\n")
        repo.write("src/app/io.py", MARK_ADAPTERS + "import app.top\n")
        out, data = roundtrip(repo)
        assert data["violations"] == []
        assert "#   app.io: CONFLICT" in out


class TestSameEdgesAsTheGate:
    """Re-export hops and dynamic imports count, as they do in the gate."""

    def test_reexport_hop_blocks_domain(self, repo: LayersRepo) -> None:
        start(repo)
        repo.write("src/app/db.py", "import subprocess\nclass Repo: ...\n")
        repo.write("src/app/__init__.py", "from app.db import Repo\n")
        repo.write("src/app/model.py", MARK_DOMAIN + "from app import Repo\n")
        out, data = roundtrip(repo)
        assert data["violations"] == []
        assert "#   app.model: CONFLICT" in out
        assert "app.model -> app.db -> subprocess" in out

    def test_dynamic_import_blocks_domain(self, repo: LayersRepo) -> None:
        start(repo)
        repo.write("src/app/db.py", "import subprocess\n")
        src = MARK_DOMAIN + "import importlib\nimportlib.import_module('app.db')\n"
        repo.write("src/app/dyn.py", src)
        out, data = roundtrip(repo)
        assert data["violations"] == []
        assert "#   app.dyn: CONFLICT" in out
        assert "app.dyn -> app.db -> subprocess" in out


class TestShadowedModules:
    """Two files with one module name are listed, never dropped."""

    def test_shadowed_file_is_listed_as_unclassified(self, repo: LayersRepo) -> None:
        start(repo)
        repo.write("src/app/a.py", "X = 1\n")
        repo.write("src/app/a/__init__.py", "Y = 2\n")
        out = repo.run("--suggest")[1]
        assert "shadow" in out
        assert "a.py" in out or "a/__init__.py" in out


class TestShadowedRoundTrip:
    """A shadowed name is unclassified as a whole: the gate sees one name."""

    def test_shadowed_io_file_does_not_make_the_name_domain(
        self, repo: LayersRepo
    ) -> None:
        start(repo)
        repo.write("src/app/a/__init__.py", "X = 1\n")
        repo.write("src/app/a.py", "import json\n")
        out, data = roundtrip(repo)
        assert data["violations"] == []
        assert "app.a" not in {m for r in rings(out).values() for m in r}
        assert "#   app.a: unclassified (shadowed: 2 files are module app.a" in out

    def test_shadowed_file_importing_an_adapter(self, repo: LayersRepo) -> None:
        start(repo)
        repo.write("src/app/db.py", "import subprocess\n")
        repo.write("src/app/a/__init__.py", "X = 1\n")
        repo.write("src/app/a.py", "import app.db\n")
        out, data = roundtrip(repo)
        assert data["violations"] == []
        assert "app.a" not in {m for r in rings(out).values() for m in r}

    def test_no_glob_over_a_shadowed_pair(self, repo: LayersRepo) -> None:
        start(repo)
        repo.write("src/app/sub/__init__.py", "")
        repo.write("src/app/sub/b.py", "X = 1\n")
        repo.write("src/app/sub/a/__init__.py", "X = 1\n")
        repo.write("src/app/sub/a.py", "import json\n")
        out, data = roundtrip(repo)
        assert data["violations"] == []
        assert "app.sub.*" not in rings(out)["domain"]

    def test_empty_conflicts_section_says_none(self, repo: LayersRepo) -> None:
        start(repo)
        for name in ("kernel", "service", "cli"):
            repo.edit(name, "import app\nfrom app import a\n")
        repo.write("src/app/a/__init__.py", "")
        repo.write("src/app/a.py", "")
        assert "# Conflicts:\n#   none" in repo.run("--suggest")[1]


class TestEvidenceMatchesTheGate:
    """Type-only imports and nested classes do not count."""

    def test_type_checking_argparse_is_not_entry(self, repo: LayersRepo) -> None:
        start(repo)
        src = (
            "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import argparse\n"
        )
        repo.edit("cli", src)
        assert "app.cli" not in rings(repo.run("--suggest")[1])["entry"]

    def test_relative_import_past_the_root_is_unclassified(
        self, repo: LayersRepo
    ) -> None:
        start(repo)
        repo.edit("kernel", "from .. import x\n")
        out = repo.run("--suggest")[1]
        assert "#   app.kernel: unclassified" in out
        assert "relative import" in out


class TestScriptsTable:
    """A malformed ``[project.scripts]`` is a one-line failure, not a traceback."""

    @pytest.mark.parametrize(
        "text",
        [
            '[project]\nscripts = "oops"\n',
            'project = "x"\n',
            "[project.scripts]\nrun = 3\n",
        ],
    )
    def test_malformed_scripts_fail_cleanly(self, repo: LayersRepo, text: str) -> None:
        start(repo)
        repo.write("pyproject.toml", text)
        code, out = repo.run("--suggest")
        assert code == 1
        assert out.startswith("FAIL:")
        assert "project.scripts" in out

    def test_missing_pyproject_is_said_in_the_header(
        self, repo: LayersRepo, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        start(repo)
        monkeypatch.setattr(LayerTable, "nearest", staticmethod(none_nearest))
        out = repo.run("--suggest")[1]
        assert "console scripts were not read" in out


class TestHeader:
    """The header warns about globs."""

    def test_glob_warning(self, repo: LayersRepo) -> None:
        start(repo)
        assert "added later" in repo.run("--suggest")[1]


class TestOutsideGit:
    """``--suggest`` uses no git, so it runs where there is no repository."""

    def test_runs_outside_a_git_repository(self, tmp_path: Path) -> None:
        pkg = tmp_path / "bare" / "src" / "app"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "a.py").write_text("import json\n")
        env = {"GIT_CEILING_DIRECTORIES": str(tmp_path), "PATH": "/usr/bin:/bin"}
        done = subprocess.run(
            [sys.executable, "-m", "oo_ratchet", "layers", str(pkg), "--suggest"],
            capture_output=True,
            text=True,
            env={**env, "HOME": str(tmp_path)},
            check=False,
        )
        assert done.returncode == 0, done.stdout + done.stderr
        assert "app.a" in done.stdout


class TestSeveralScripts:
    """Every script that targets a module is named in its entry reason."""

    def test_all_script_names_are_kept(self, repo: LayersRepo) -> None:
        start(repo)
        scripts = (
            PROJECT.split("[project.scripts]")[0]
            + "[project.scripts]\n"
            + 'zed = "app.runner:other"\napp-run = "app.runner:main"\n'
        )
        repo.write("pyproject.toml", scripts)
        repo.write("src/app/runner.py", "")
        out = repo.run("--suggest")[1]
        assert "console script app-run, console script zed" in out


class TestPackageRoot:
    """The root is placed: adopters list it, and the design check wants it layered."""

    def test_root_is_entry(self, repo: LayersRepo) -> None:
        start(repo)
        out = repo.run("--suggest")[1]
        assert "app" in rings(out)["entry"]

    def test_root_imported_by_a_non_entry_module_is_unclassified(
        self, repo: LayersRepo
    ) -> None:
        start(repo)
        repo.write("src/app/__init__.py", "from app.kernel import K\n")
        repo.edit("kernel", "class K: ...\n")
        repo.edit("service", "from app import K\n")
        out = repo.run("--suggest")[1]
        assert "app" not in rings(out)["entry"]
        assert "#   app: unclassified (" in out

    def test_design_check_and_gate_accept_the_table(self, repo: LayersRepo) -> None:
        start(repo)
        repo.write("src/app/__init__.py", "from app import kernel\n")
        repo.edit("cli", "import argparse\n")
        repo.edit("service", "import json\n")
        _, data = roundtrip(repo)
        assert data["violations"] == []
        code, text = design(repo)
        assert code == 0, text
        unlayered = [
            f for f in json.loads(text)["findings"] if f["rule"] == "unlayered-module"
        ]
        assert not any(f["path"].endswith("app/__init__.py") for f in unlayered)


def design(repo: LayersRepo) -> tuple[int, str]:
    """Run the design check on the package; return its exit code and stdout."""
    from oo_ratchet.design.cli import main

    repo._out.readouterr()
    code = main([str(repo.root / "src" / "app"), "--json"])
    return code, repo._out.readouterr().out


class TestSingleModulePackage:
    """A namespace root with one module and no initializer is a package."""

    @staticmethod
    def package(tmp_path: Path) -> Path:
        pkg = tmp_path / "src" / "pkg"
        pkg.mkdir(parents=True)
        (pkg / "one.py").write_text('__ring__ = "domain"\n')
        (tmp_path / "pyproject.toml").write_text(PROJECT)
        GitSandbox(tmp_path).commit("one")
        return pkg

    def test_one_module_without_a_root_initializer(self, tmp_path: Path) -> None:
        assert (
            main([str(self.package(tmp_path)), "--namespace", "pkg", "--suggest"]) == 0
        )

    def test_round_trips_through_the_gate(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        pkg = self.package(tmp_path)
        assert main([str(pkg), "--namespace", "pkg", "--suggest"]) == 0
        out = capsys.readouterr().out
        (tmp_path / "pyproject.toml").write_text(PROJECT + "\n" + out)
        assert main([str(pkg), "--namespace", "pkg", "--json"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert (data["violations"], data["unassigned"]) == ([], [])


class TestGlobMetacharacters:
    """A module name is matched literally by the gate's fnmatch, so escape it."""

    def test_bracket_name_and_its_lookalike_keep_their_own_rings(
        self, repo: LayersRepo
    ) -> None:
        start(repo)
        for other in ("kernel", "service", "cli"):
            repo.edit(other, MARK_DOMAIN)
        repo.write("src/app/plugin[old].py", MARK_ADAPTERS)
        repo.write("src/app/plugino.py", MARK_DOMAIN)
        repo.write("src/app/a*b.py", MARK_ADAPTERS)
        repo.write("src/app/x?.py", MARK_ADAPTERS)
        out, data = roundtrip(repo)
        assert data["violations"] == []
        assert data["unassigned"] == []
        config = LayerTable.from_text(PROJECT + "\n" + out, "t")
        assert config is not None
        assert config.layer("app.plugin[old]") == "adapters"
        assert config.layer("app.plugino") == "domain"
        assert config.layer("app.a*b") == "adapters"
        assert config.layer("app.x?") == "adapters"


class TestNoGitNeeded:
    """``--suggest`` never runs git: not even to find the repository."""

    @staticmethod
    def package(tmp_path: Path) -> Path:
        pkg = tmp_path / "src" / "app"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "a.py").write_text("import json\n")
        return pkg

    def test_no_subprocess_is_started(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pkg = self.package(tmp_path)

        def boom(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("--suggest started a subprocess")

        monkeypatch.setattr(subprocess, "run", boom)
        monkeypatch.setattr(subprocess, "Popen", boom)
        assert main([str(pkg), "--suggest"]) == 0

    def test_runs_with_git_off_the_path(self, tmp_path: Path) -> None:
        pkg = self.package(tmp_path)
        empty = tmp_path / "empty"
        empty.mkdir()
        env = {"PATH": str(empty), "HOME": str(tmp_path)}
        done = subprocess.run(
            [sys.executable, "-m", "oo_ratchet", "layers", str(pkg), "--suggest"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        assert done.returncode == 0, done.stdout + done.stderr
        assert "app.a" in done.stdout


class TestRootScripts:
    """A script that targets the package initializer stays in the root's reason."""

    def test_root_reason_names_the_script(self, repo: LayersRepo) -> None:
        start(repo)
        text = '[project]\nname = "app"\n[project.scripts]\ntool = "app:main"\n'
        repo.write("pyproject.toml", text)
        out = repo.run("--suggest")[1]
        assert "#   app: entry (" in out
        assert "console script tool" in out
