"""``layers --suggest``: a starter ring table, printed for review, never applied."""

from __future__ import annotations

import tomllib

from tests.layers_repo import LayersRepo

PROJECT = """\
[project]
name = "app"
version = "0"

[project.scripts]
app-run = "app.runner:main"
"""
PROTOCOL = "from typing import Protocol\n\n\nclass Store(Protocol):\n    ...\n"


def rings(out: str) -> dict[str, list[str]]:
    """Parse the ring table out of the suggestion text."""
    table = tomllib.loads(out)
    found: dict[str, list[str]] = table["tool"]["oo-ratchet"]["layers"]
    return found


def start(repo: LayersRepo) -> None:
    """Replace the repo's modules with an unconfigured package and commit."""
    repo.write("pyproject.toml", PROJECT)
    for name in ("kernel", "service", "cli"):
        repo.edit(name, "")
    repo.commit()


class TestRules:
    """One test per ring rule, plus the order and the unclassifiable case."""

    def test_argparse_is_entry(self, repo: LayersRepo) -> None:
        start(repo)
        repo.edit("cli", "import argparse\n")
        code, out = repo.run("--suggest")
        assert code == 0
        assert rings(out)["entry"] == ["app.cli"]
        assert "app.cli: entry (imports argparse)" in out

    def test_typer_is_entry(self, repo: LayersRepo) -> None:
        start(repo)
        repo.edit("cli", "from typer import Typer\n")
        assert rings(repo.run("--suggest")[1])["entry"] == ["app.cli"]

    def test_console_script_target_is_entry(self, repo: LayersRepo) -> None:
        start(repo)
        repo.edit("runner", "")
        code, out = repo.run("--suggest")
        assert code == 0
        assert rings(out)["entry"] == ["app.runner"]
        assert "console script app-run" in out

    def test_io_import_is_adapters(self, repo: LayersRepo) -> None:
        start(repo)
        repo.edit("service", "import json\n")
        out = repo.run("--suggest")[1]
        assert rings(out)["adapters"] == ["app.service"]
        assert "app.service: adapters (imports IO: json)" in out

    def test_open_call_is_adapters(self, repo: LayersRepo) -> None:
        start(repo)
        repo.edit("service", "def read(p):\n    return open(p)\n")
        assert rings(repo.run("--suggest")[1])["adapters"] == ["app.service"]

    def test_protocol_imported_by_an_adapter_is_application(
        self, repo: LayersRepo
    ) -> None:
        start(repo)
        repo.edit("kernel", PROTOCOL)
        repo.edit("service", "import json\nimport app.kernel\n")
        out = repo.run("--suggest")[1]
        assert rings(out)["application"] == ["app.kernel"]
        assert "app.kernel: application (defines Protocol Store" in out

    def test_protocol_no_adapter_imports_is_domain(self, repo: LayersRepo) -> None:
        start(repo)
        repo.edit("kernel", PROTOCOL)
        out = repo.run("--suggest")[1]
        assert "app.kernel" in rings(out)["domain"]
        assert "no adapter imports it" in out

    def test_pure_module_is_domain(self, repo: LayersRepo) -> None:
        start(repo)
        repo.edit("kernel", "X = 1\n")
        out = repo.run("--suggest")[1]
        assert rings(out)["domain"] == ["app.cli", "app.kernel", "app.service"]
        assert "app.kernel: domain (no IO, no adapter imports)" in out

    def test_entry_wins_over_adapters_and_says_so(self, repo: LayersRepo) -> None:
        start(repo)
        repo.edit("cli", "import argparse\nimport json\n")
        out = repo.run("--suggest")[1]
        assert rings(out)["entry"] == ["app.cli"]
        assert "rings it also matched: adapters (imports IO: json)" in out

    def test_unclassifiable_module_is_a_comment_not_a_guess(
        self, repo: LayersRepo
    ) -> None:
        start(repo)
        repo.edit("service", "import json\n")
        repo.edit("kernel", "import app.service\n")
        code, out = repo.run("--suggest")
        assert code == 0
        table = rings(out)
        assert "app.kernel" not in {m for ring in table.values() for m in ring}
        assert "# app.kernel: unclassified (domain may import only domain" in out

    def test_exact_prefix_glob_only_when_every_module_under_it_agrees(
        self, repo: LayersRepo
    ) -> None:
        start(repo)
        repo.write("src/app/pure/__init__.py", "")
        repo.write("src/app/pure/a.py", "")
        repo.write("src/app/pure/b.py", "")
        repo.write("src/app/mixed/__init__.py", "")
        repo.write("src/app/mixed/a.py", "")
        repo.write("src/app/mixed/b.py", "import json\n")
        table = rings(repo.run("--suggest")[1])
        assert "app.pure.*" in table["domain"]
        assert "app.pure" in table["domain"]
        assert "app.mixed.a" in table["domain"]
        assert "app.mixed.b" in table["adapters"]
        assert not any("app.mixed.*" in ring for ring in table.values())


class TestSafety:
    """The suggestion prints; it changes nothing and is stable."""

    def test_writes_nothing(self, repo: LayersRepo) -> None:
        start(repo)
        before = repo._sandbox.run_git("status", "--porcelain", "--ignored")
        pyproject = (repo.root / "pyproject.toml").read_text()
        code, _ = repo.run("--suggest")
        assert code == 0
        assert repo._sandbox.run_git("status", "--porcelain", "--ignored") == before
        assert (repo.root / "pyproject.toml").read_text() == pyproject
        assert not repo.baseline.exists()

    def test_output_is_deterministic(self, repo: LayersRepo) -> None:
        start(repo)
        repo.edit("service", "import json\n")
        repo.edit("kernel", "import app.service\n")
        assert repo.run("--suggest") == repo.run("--suggest")

    def test_needs_no_existing_layers_table(self, repo: LayersRepo) -> None:
        start(repo)
        code, out = repo.run("--suggest")
        assert (code, out.startswith("# ")) == (0, True)

    def test_says_it_is_not_applied(self, repo: LayersRepo) -> None:
        start(repo)
        out = repo.run("--suggest")[1]
        assert "never applied" in out

    def test_refuses_to_combine_with_check(self, repo: LayersRepo) -> None:
        start(repo)
        try:
            repo.run("--suggest", "--check")
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError("--suggest --check was accepted")


class TestRoundTrip:
    """The printed table is valid input to the layers gate."""

    def test_the_gate_reads_what_suggest_prints(self, repo: LayersRepo) -> None:
        start(repo)
        repo.edit("cli", "import argparse\n")
        repo.edit("service", "import json\n")
        repo.edit("kernel", "X = 1\n")
        out = repo.run("--suggest")[1]
        repo.write("pyproject.toml", PROJECT + "\n" + out)
        code, report = repo.run()
        assert code == 0, report
        assert "Unassigned modules: 0" in report
        code, _ = repo.run("--json")
        assert code == 0
