"""The layers gate baselines a domain module's IO imports as violating edges."""

from __future__ import annotations

import json

from tests.layers_repo import LayersRepo

FIXED = """\
[tool.oo-ratchet.layers]
entry = ["app.cli"]
domain = ["app.domain"]
"""
PURE = "X = 1\n"
IMPURE = "import subprocess\n"
EDGE = "app.domain -> subprocess"


def _setup(repo: LayersRepo, domain: str, entry: str = "import app.domain\n") -> None:
    """Make ``app`` a fixed-form package of exactly a cli and a domain module."""
    repo.write("pyproject.toml", FIXED)
    repo.write("src/app/domain.py", domain)
    repo.write("src/app/cli.py", entry)
    (repo.root / "src/app/kernel.py").unlink()
    (repo.root / "src/app/service.py").unlink()


class TestDomainPurity:
    """A domain module importing an IO module is an edge the baseline tracks."""

    def test_new_io_import_in_domain_fails_check(self, repo: LayersRepo) -> None:
        _setup(repo, PURE)
        repo.adopt()
        repo.write("src/app/domain.py", IMPURE)
        code, out = repo.run("--check")
        assert code == 1
        assert EDGE in out

    def test_baselined_io_import_passes(self, repo: LayersRepo) -> None:
        _setup(repo, IMPURE)
        repo.adopt()
        assert json.loads(repo.baseline.read_text()) == {"app.domain": ["subprocess"]}
        code, out = repo.run("--check")
        assert (code, "PASS" in out) == (0, True)

    def test_removed_io_import_is_a_stale_entry(self, repo: LayersRepo) -> None:
        _setup(repo, IMPURE)
        repo.adopt()
        repo.write("src/app/domain.py", PURE)
        code, out = repo.run("--check")
        assert code == 1
        assert "no longer violate" in out
        assert repo.run("--update")[0] == 0
        assert json.loads(repo.baseline.read_text()) == {}

    def test_bare_open_in_domain_is_an_edge(self, repo: LayersRepo) -> None:
        _setup(repo, PURE)
        repo.adopt()
        repo.write("src/app/domain.py", "def f():\n    return open('x')\n")
        code, out = repo.run("--check")
        assert code == 1
        assert "app.domain -> builtins.open" in out

    def test_io_import_outside_domain_is_not_an_edge(self, repo: LayersRepo) -> None:
        _setup(repo, PURE, "import app.domain\nimport subprocess\n")
        repo.adopt()
        code, out = repo.run("--check")
        assert (code, "PASS" in out) == (0, True)
