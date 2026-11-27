"""The base module list comes from the committed tree, not an exported scan."""

from __future__ import annotations

import os
from pathlib import Path

from oo_ratchet.layers.gitio import LayersGit
from oo_ratchet.layers.ratchet import LayersRatchet
from oo_ratchet.layers.scan import LayerScan
from tests.layers_repo import LayersRepo

TABLE = """\
[tool.oo-ratchet.layers]
entry = ["app.cli"]
adapters = ["app.store"]
domain = ["app", "app.domain", "app.thing"]
"""
PROMOTED = TABLE.replace(
    'adapters = ["app.store"]', 'adapters = ["app.store", "app.thing"]'
)
ANY = """\
[tool.oo-ratchet.layers]
entry = ["*.cli"]
adapters = ["*.store"]
domain = ["*"]
"""
ANY_PROMOTED = ANY.replace(
    'adapters = ["*.store"]', 'adapters = ["*.store", "*.thing"]'
)
MODULES = {
    "cli": "import app.domain\n",
    "domain": "X = 1\n",
    "thing": "Y = 1\n",
    "store": "Z = 1\n",
}


def _package(repo: LayersRepo, table: str, where: str = "src/app") -> None:
    """Replace the fixture package with a clean one at ``where``."""
    for old in (repo.root / "src/app").glob("*.py"):
        if where != "src/app" or old.stem in ("kernel", "service", "cli"):
            old.unlink()
    repo.write("pyproject.toml", table)
    repo.write(f"{where}/__init__.py", "")
    for name, text in MODULES.items():
        repo.write(f"{where}/{name}.py", text)


def _adopted(repo: LayersRepo, table: str, where: str = "src/app") -> None:
    _package(repo, table, where)
    repo.adopt()
    repo.commit_as_origin_main()


class TestCommittedTree:
    """Tracked files count at the base whatever git archive would export."""

    def test_export_ignored_module_still_counts_as_existing(
        self, repo: LayersRepo
    ) -> None:
        repo.write(".gitattributes", "src/app/thing.py export-ignore\n")
        _adopted(repo, TABLE)
        repo.write("pyproject.toml", PROMOTED)
        code, out = repo.run("--check")
        assert code == 1
        assert "app.thing" in out

    def test_base_holding_only_the_initializer_is_comparable(
        self, repo: LayersRepo
    ) -> None:
        _package(repo, TABLE)
        repo.adopt()
        for name in MODULES:
            (repo.root / "src/app" / f"{name}.py").unlink()
        repo.commit_as_origin_main()
        for name, text in MODULES.items():
            repo.write(f"src/app/{name}.py", text)
        code, out = repo.run("--check")
        assert "no modules to check" not in out
        assert code == 0, out


class TestWhereThePackageLives:
    """The base package is found at the repository root or after a move."""

    def test_root_package_move_is_detected(self, repo: LayersRepo) -> None:
        _package(repo, ANY, where=".")
        repo.commit_as_origin_main()
        assert repo.run_on(repo.root, "--update")[0] == 0
        repo.commit_as_origin_main()
        repo.write("pyproject.toml", ANY_PROMOTED)
        code, out = repo.run_on(repo.root, "--check")
        assert code == 1, out
        assert ".thing" in out

    def test_relocated_package_move_is_detected(self, repo: LayersRepo) -> None:
        _adopted(repo, TABLE)
        for name in ("__init__", *MODULES):
            (repo.root / "src/app" / f"{name}.py").unlink()
            repo.write(
                f"lib/app/{name}.py", "" if name == "__init__" else MODULES[name]
            )
        repo.write("pyproject.toml", PROMOTED)
        code, out = repo.run_on(repo.root / "lib" / "app", "--check")
        assert code == 1, out
        assert "app.thing" in out

    def test_two_candidate_base_packages_fail_closed(self, repo: LayersRepo) -> None:
        _adopted(repo, TABLE)
        repo.write("other/app/__init__.py", "")
        repo.write("other/app/x.py", "")
        repo.commit_as_origin_main()
        for name in ("__init__", *MODULES):
            (repo.root / "src/app" / f"{name}.py").unlink()
            repo.write(
                f"lib/app/{name}.py", "" if name == "__init__" else MODULES[name]
            )
        code, out = repo.run_on(repo.root / "lib" / "app", "--check")
        assert code == 1
        assert "more than one" in out


class TestPlainPackageEdges:
    """Stray files, nested namesakes and a missing initializer at the base."""

    def test_non_utf8_filename_elsewhere_does_not_block(self, repo: LayersRepo) -> None:
        repo.write(os.fsdecode(b"stray\xff.txt"), "x\n")
        _adopted(repo, TABLE)
        repo.write("pyproject.toml", PROMOTED)
        code, out = repo.run("--check")
        assert code == 1
        assert "app.thing" in out

    def test_nested_namesake_is_not_a_candidate(self, repo: LayersRepo) -> None:
        _adopted(repo, TABLE)
        repo.write("pkg/__init__.py", "")
        repo.write("pkg/vendor/app/__init__.py", "")
        repo.commit_as_origin_main()
        for name in ("__init__", *MODULES):
            (repo.root / "src/app" / f"{name}.py").unlink()
            repo.write(
                f"lib/app/{name}.py", "" if name == "__init__" else MODULES[name]
            )
        repo.write("pyproject.toml", PROMOTED)
        code, out = repo.run_on(repo.root / "lib" / "app", "--check")
        assert "more than one" not in out
        assert code == 1
        assert "app.thing" in out

    def test_base_without_an_initializer_still_compares(self, repo: LayersRepo) -> None:
        _package(repo, TABLE)
        repo.adopt()
        (repo.root / "src/app/__init__.py").unlink()
        repo.commit_as_origin_main()
        repo.write("src/app/__init__.py", "")
        repo.write("pyproject.toml", PROMOTED)
        code, out = repo.run("--check")
        assert code == 1, out
        assert "app.thing" in out


class TestNamespaceMode:
    """A namespace selection compares every current module: strict, no history."""

    def test_new_adapter_needs_the_flag(self, repo: LayersRepo) -> None:
        _adopted(repo, TABLE.replace('"app.thing"]', '"app.thing", "app.fresh"]'))
        repo.write("src/app/fresh.py", "W = 1\n")
        repo.write(
            "pyproject.toml",
            TABLE.replace(
                'adapters = ["app.store"]', 'adapters = ["app.store", "app.fresh"]'
            ),
        )
        src = repo.root / "src" / "app"
        refused = repo.run_on(src, "--namespace", "app", "--check")
        assert refused[0] == 1
        assert "app.fresh" in refused[1]
        waived = repo.run_on(
            src, "--namespace", "app", "--check", "--allow-config-change"
        )
        assert waived[0] == 0, waived[1]


class TestDirectCallers:
    """``LayersRatchet`` works without a base-modules callback."""

    def test_default_treats_every_current_module_as_existing(
        self, repo: LayersRepo
    ) -> None:
        _adopted(repo, TABLE)
        repo.write("pyproject.toml", PROMOTED)
        src: Path = repo.root / "src" / "app"
        outcome = LayersRatchet(repo.root, LayersGit(repo.root)).check(
            LayerScan(src), base_ref="origin/main", require_base=True
        )
        assert outcome.exit_code == 1
        assert any("app.thing" in line for line in outcome.lines)
