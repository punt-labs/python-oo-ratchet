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

    def test_dynamic_import_of_io_in_domain_is_an_edge(self, repo: LayersRepo) -> None:
        _setup(repo, PURE)
        repo.adopt()
        body = "import importlib\nA = importlib.import_module('subprocess')\n"
        repo.write("src/app/domain.py", body + "B = __import__('socket')\n")
        code, out = repo.run("--check")
        assert code == 1
        assert "app.domain -> subprocess" in out
        assert "app.domain -> socket" in out

    def test_builtins_open_attribute_in_domain_is_an_edge(
        self, repo: LayersRepo
    ) -> None:
        _setup(repo, PURE)
        repo.adopt()
        body = "import builtins\n\n\ndef f():\n    return builtins.open('x')\n"
        repo.write("src/app/domain.py", body)
        code, out = repo.run("--check")
        assert code == 1
        assert "app.domain -> builtins.open" in out


ENTRY_EDGE = "app.domain -> app.cli"
LEAKY = "import app.cli\n"
FLAG = "--allow-config-change"
BASE = ("--base-ref", "HEAD", "--require-base")


def _upgrade(repo: LayersRepo, baseline: dict[str, list[str]]) -> None:
    """A domain module that already imports IO, under a baseline from before."""
    _setup(repo, IMPURE + LEAKY if baseline else IMPURE)
    repo.baseline.write_text(json.dumps(baseline))
    repo.commit_as_origin_main()


class TestAdopterUpgrade:
    """An adopter whose domain already imports IO gets one audited way in."""

    def test_update_with_rows_refuses_io_growth_without_the_flag(
        self, repo: LayersRepo
    ) -> None:
        _upgrade(repo, {"app.domain": ["app.cli"]})
        code, out = repo.run("--update")
        assert code == 1
        assert EDGE in out

    def test_update_with_rows_accepts_io_growth_with_the_flag(
        self, repo: LayersRepo
    ) -> None:
        _upgrade(repo, {"app.domain": ["app.cli"]})
        assert repo.run("--update", FLAG)[0] == 0
        assert json.loads(repo.baseline.read_text()) == {
            "app.domain": ["app.cli", "subprocess"]
        }
        entry = repo.audit[-1]
        assert entry["config_change"] is True
        assert entry["added"] == [EDGE]

    def test_flag_does_not_allow_growth_of_a_non_io_edge(
        self, repo: LayersRepo
    ) -> None:
        _upgrade(repo, {"app.domain": ["app.cli"]})
        repo.write("src/app/domain.py", IMPURE + LEAKY + "import app.entry\n")
        repo.write("src/app/entry.py", "")
        repo.write(
            "pyproject.toml", FIXED.replace('["app.cli"]', '["app.cli", "app.entry"]')
        )
        code, out = repo.run("--update", FLAG)
        assert code == 1
        assert "app.domain -> app.entry" in out
        assert EDGE not in out

    def test_zero_rows_check_fails_without_the_flag(self, repo: LayersRepo) -> None:
        _upgrade(repo, {})
        assert repo.run("--update")[0] == 0
        code, out = repo.run("--check", *BASE)
        assert code == 1
        assert "did not" in out

    def test_zero_rows_update_then_check_pass_with_the_flag(
        self, repo: LayersRepo
    ) -> None:
        _upgrade(repo, {})
        assert repo.run("--update", FLAG)[0] == 0
        code, out = repo.run("--check", FLAG, *BASE)
        assert (code, "PASS" in out) == (0, True)

    def test_flag_check_still_fails_on_non_io_growth(self, repo: LayersRepo) -> None:
        _upgrade(repo, {})
        assert repo.run("--update", FLAG)[0] == 0
        repo.write("src/app/domain.py", IMPURE + LEAKY)
        repo.baseline.write_text(json.dumps({"app.domain": ["app.cli", "subprocess"]}))
        code, out = repo.run("--check", FLAG, *BASE)
        assert code == 1
        assert ENTRY_EDGE in out
