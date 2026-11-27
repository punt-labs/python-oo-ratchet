"""``layers --suggest`` must agree with the gate: no table that fails on itself."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from oo_ratchet.design.layer_table import LayerTable
from tests.layers_repo import LayersRepo
from tests.test_layers_suggest import PROJECT, PROTOCOL, rings, start


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
    """The reviewers' repro: ports, model, db, cli, mid, user."""
    start(repo)
    repo.write("src/app/ports.py", PROTOCOL)
    repo.write("src/app/model.py", "from app.ports import Store\n")
    repo.write(
        "src/app/db.py", "import subprocess\nimport app.ports\nimport app.model\n"
    )
    repo.write("src/app/runner.py", "import argparse\n")
    repo.write("src/app/mid.py", "from app import db\n")
    repo.write("src/app/user.py", "from app import mid\n")


class TestNoSelfViolations:
    """A module is placed only where the gate would accept its imports."""

    def test_repro_package_has_no_violations(self, repo: LayersRepo) -> None:
        layered(repo)
        out, data = roundtrip(repo)
        assert data["violations"] == []
        table = rings(out)
        placed = {m for ring in table.values() for m in ring}
        assert "app.user" not in placed
        assert "app.model" not in placed
        assert "unclassified" in out

    def test_importer_of_an_application_module_is_not_domain(
        self, repo: LayersRepo
    ) -> None:
        layered(repo)
        assert "app.model" not in rings(repo.run("--suggest")[1])["domain"]

    def test_unclassified_importers_are_unclassified_in_turn(
        self, repo: LayersRepo
    ) -> None:
        layered(repo)
        out = repo.run("--suggest")[1]
        assert "# app.user: unclassified" in out
        assert "# app.mid: unclassified" in out

    def test_second_package_has_no_violations(self, repo: LayersRepo) -> None:
        start(repo)
        repo.write("src/app/core/__init__.py", "")
        repo.write("src/app/core/rules.py", "X = 1\n")
        repo.write("src/app/core/calc.py", "from app.core import rules\n")
        repo.write("src/app/ports.py", PROTOCOL)
        repo.write("src/app/store.py", "import sqlite3\nfrom app.ports import Store\n")
        repo.write("src/app/helper.py", "import app.store\n")
        repo.write("src/app/top.py", "import typer\nimport app.helper\n")
        repo.write("src/app/svc.py", "import app.ports\nimport app.core.calc\n")
        out, data = roundtrip(repo)
        assert data["violations"] == []
        assert "app.core.calc" in out

    def test_adapter_importing_an_entry_module_is_unclassified(
        self, repo: LayersRepo
    ) -> None:
        start(repo)
        repo.write("src/app/top.py", "import argparse\n")
        repo.write("src/app/io.py", "import json\nimport app.top\n")
        out, data = roundtrip(repo)
        assert data["violations"] == []
        assert "# app.io: unclassified" in out


class TestSameEdgesAsTheGate:
    """Re-export hops and dynamic imports count, as they do in the gate."""

    def test_reexport_hop_blocks_domain(self, repo: LayersRepo) -> None:
        start(repo)
        repo.write("src/app/db.py", "import subprocess\nclass Repo: ...\n")
        repo.write("src/app/__init__.py", "from app.db import Repo\n")
        repo.write("src/app/model.py", "from app import Repo\n")
        out, data = roundtrip(repo)
        assert data["violations"] == []
        assert "app.model" not in rings(out)["domain"]

    def test_dynamic_import_blocks_domain(self, repo: LayersRepo) -> None:
        start(repo)
        repo.write("src/app/db.py", "import subprocess\n")
        src = "import importlib\nimportlib.import_module('app.db')\n"
        repo.write("src/app/dyn.py", src)
        out, data = roundtrip(repo)
        assert data["violations"] == []
        assert "app.dyn" not in rings(out)["domain"]

    def test_reexport_hop_makes_application(self, repo: LayersRepo) -> None:
        start(repo)
        repo.write("src/app/ports.py", PROTOCOL)
        repo.write("src/app/__init__.py", "from app.ports import Store\n")
        repo.write("src/app/db.py", "import subprocess\nfrom app import Store\n")
        out = repo.run("--suggest")[1]
        assert rings(out)["application"] == ["app.ports"]


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
        assert "# app.a: unclassified (shadowed: 2 files are module app.a" in out

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

    def test_empty_reasons_section_says_none(self, repo: LayersRepo) -> None:
        start(repo)
        for name in ("kernel", "service", "cli"):
            repo.edit(name, "import app\nfrom app import a\n")
        repo.write("src/app/a/__init__.py", "")
        repo.write("src/app/a.py", "")
        assert repo.run("--suggest")[1].rstrip().endswith("# Reasons:\n#   none")


class TestEvidenceMatchesTheGate:
    """Type-only imports and nested classes do not count."""

    def test_type_checking_argparse_is_not_entry(self, repo: LayersRepo) -> None:
        start(repo)
        src = (
            "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import argparse\n"
        )
        repo.edit("cli", src)
        assert "app.cli" not in rings(repo.run("--suggest")[1])["entry"]

    def test_nested_protocol_is_not_a_protocol(self, repo: LayersRepo) -> None:
        start(repo)
        src = "from typing import Protocol\ndef f():\n    class P(Protocol): ...\n"
        repo.edit("kernel", src)
        repo.edit("service", "import json\nimport app.kernel\n")
        assert rings(repo.run("--suggest")[1])["application"] == []

    def test_relative_import_past_the_root_is_unclassified(
        self, repo: LayersRepo
    ) -> None:
        start(repo)
        repo.edit("kernel", "from .. import x\n")
        out = repo.run("--suggest")[1]
        assert "# app.kernel: unclassified" in out
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


class TestProtocolBindings:
    """A base is a Protocol only if it resolves to typing's Protocol."""

    @staticmethod
    def adapter_imports_kernel(repo: LayersRepo, source: str) -> list[str]:
        start(repo)
        repo.edit("kernel", source)
        repo.edit("service", "import json\nimport app.kernel\n")
        return rings(repo.run("--suggest")[1])["application"]

    @pytest.mark.parametrize(
        "source",
        [
            "from typing import Protocol as Port\n\n\nclass P(Port): ...\n",
            "import typing as t\n\n\nclass P(t.Protocol): ...\n",
            "import typing\n\n\nclass P(typing.Protocol): ...\n",
            "from typing_extensions import Protocol\n\n\nclass P(Protocol): ...\n",
            "import typing_extensions as te\n\n\nclass P(te.Protocol): ...\n",
            "from typing import Protocol\n\n\nclass P(Protocol[int]): ...\n",
        ],
    )
    def test_resolved_protocol_is_application(
        self, repo: LayersRepo, source: str
    ) -> None:
        assert self.adapter_imports_kernel(repo, source) == ["app.kernel"]

    @pytest.mark.parametrize(
        "source",
        [
            "from other import Protocol\n\n\nclass P(Protocol): ...\n",
            "import other\n\n\nclass P(other.Protocol): ...\n",
            "class Protocol: ...\n\n\nclass P(Protocol): ...\n",
        ],
    )
    def test_lookalike_is_not_a_port(self, repo: LayersRepo, source: str) -> None:
        assert self.adapter_imports_kernel(repo, source) == []


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
        assert "# app: unclassified (" in out

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
