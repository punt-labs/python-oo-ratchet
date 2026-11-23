"""Review findings on the layers gate: scoping, atomicity and import recognition."""

from __future__ import annotations

from pathlib import Path

import pytest

from oo_ratchet.design.layer_edges import Edge
from oo_ratchet.layers.cli import main
from oo_ratchet.layers.report import LayersReport
from oo_ratchet.layers.scan import LayerScan
from tests.conftest import GitSandbox
from tests.layers_repo import BAD_SERVICE, OK_SERVICE, PYPROJECT, LayersRepo

DECLARED = """\
[tool.oo-ratchet.layers.kernel]
prefixes = ["kernel"]
imports = []

[tool.oo-ratchet.layers.service]
prefixes = ["service"]
imports = ["kernel"]
"""


def _package(tmp_path: Path, files: dict[str, str]) -> Path:
    (tmp_path / "pyproject.toml").write_text(DECLARED)
    pkg = tmp_path / "src" / "app"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    for name, text in files.items():
        path = pkg / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return pkg


def _violation(tmp_path: Path, kernel: str, **extra: str) -> bool:
    files = {"kernel.py": kernel, "service.py": "", **extra}
    return (
        Edge("app.kernel", "app.service") in LayerScan(_package(tmp_path, files)).edges
    )


class TestBaselineScope:
    """The baseline belongs to the scanned package's repository and package."""

    def _checkout(self, root: Path) -> GitSandbox:
        root.mkdir()
        other = GitSandbox(root)
        other.write("pyproject.toml", PYPROJECT)
        other.write("src/app/__init__.py", "")
        other.write("src/app/kernel.py", "")
        other.write("src/app/service.py", OK_SERVICE)
        other.write("src/app/cli.py", "")
        return other

    def test_src_in_another_checkout_writes_that_checkouts_baseline(
        self, repo: LayersRepo
    ) -> None:
        other = self._checkout(repo.root / "other")
        code, _ = repo.run_on(other.root / "src" / "app", "--update")
        assert code == 0
        assert (other.root / ".oo-layers-baseline.json").exists()
        assert not repo.baseline.exists()

    def test_src_outside_any_repository_is_refused(
        self,
        repo: LayersRepo,
        tmp_path_factory: pytest.TempPathFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        outside = tmp_path_factory.mktemp("outside")
        monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(outside.parent))
        pkg = outside / "src" / "app"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "kernel.py").write_text("")
        (outside / "pyproject.toml").write_text(PYPROJECT)
        (repo.root / "linked").symlink_to(pkg)
        code, out = repo.run_on(repo.root / "linked", "--update")
        assert code == 1
        assert "git repository" in out
        assert not repo.baseline.exists()

    def test_updating_a_clean_second_package_keeps_the_first_packages_rows(
        self, repo: LayersRepo
    ) -> None:
        for name, text in {
            "__init__": "",
            "kernel": "",
            "service": OK_SERVICE.replace("app", "app2"),
            "cli": "",
        }.items():
            repo.write(f"src/app2/{name}.py", text)
        second = repo.root / "src" / "app2"
        repo.commit_as_origin_main()
        assert repo.run("--update")[0] == 0
        repo.commit_as_origin_main()
        assert repo.run_on(second, "--update")[0] == 0
        repo.commit_as_origin_main()
        assert repo.run("--check")[0] == 0
        assert repo.run_on(second, "--check")[0] == 0

    def test_deleted_baseline_fails_even_for_a_clean_package(
        self, repo: LayersRepo
    ) -> None:
        repo.edit("kernel", "")
        repo.commit_as_origin_main()
        assert repo.run("--update")[0] == 0
        repo.commit_as_origin_main()
        repo.baseline.unlink()
        code, out = repo.run("--check", "--base-ref", "HEAD")
        assert code == 1
        assert "baseline" in out


class TestAtomicUpdate:
    """A failed audit append leaves the previous baseline in place."""

    def test_existing_baseline_is_restored(self, repo: LayersRepo) -> None:
        repo.adopt()
        before = repo.baseline.read_text()
        repo.edit("kernel", "")
        audit = repo.root / ".oo-layers-audit.jsonl"
        audit.unlink()
        audit.mkdir()
        code, out = repo.run("--update")
        assert code == 1
        assert "FAIL" in out
        assert repo.baseline.read_text() == before

    def test_absent_baseline_stays_absent(self, repo: LayersRepo) -> None:
        (repo.root / ".oo-layers-audit.jsonl").mkdir()
        code, _ = repo.run("--update")
        assert code == 1
        assert not repo.baseline.exists()


class TestExternalConfig:
    """A layer config outside the repository is a controlled failure."""

    def test_pyproject_above_the_repository_fails_cleanly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(PYPROJECT)
        inner = tmp_path / "inner"
        inner.mkdir()
        box = GitSandbox(inner)
        for name, text in {
            "__init__": "",
            "kernel": "",
            "service": OK_SERVICE,
            "cli": "",
        }.items():
            box.write(f"src/app/{name}.py", text)
        monkeypatch.chdir(inner)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        box.commit("one")
        src = str(inner / "src" / "app")
        assert main([src, "--update"]) == 0
        box.commit("two")
        assert main([src, "--check", "--base-ref", "HEAD"]) == 1


class TestPolicyWidening:
    """Widening a layer's imports needs its own reviewed change."""

    def _widened(self, repo: LayersRepo) -> None:
        repo.edit("kernel", "")
        repo.adopt()
        repo.commit_as_origin_main()
        repo.write(
            "pyproject.toml",
            PYPROJECT.replace(
                'prefixes = ["kernel"]\nimports = []',
                'prefixes = ["kernel"]\nimports = ["service"]',
            ),
        )

    def test_widening_without_a_new_edge_fails(self, repo: LayersRepo) -> None:
        self._widened(repo)
        code, out = repo.run("--check")
        assert code == 1
        assert "widened" in out
        assert "--allow-config-change" in out

    def test_allow_config_change_waives_the_failure(self, repo: LayersRepo) -> None:
        self._widened(repo)
        assert repo.run("--check", "--allow-config-change")[0] == 0

    def test_update_records_the_config_change_in_the_audit(
        self, repo: LayersRepo
    ) -> None:
        repo.adopt()
        assert repo.run("--update", "--allow-config-change")[0] == 0
        assert repo.audit[-1]["config_change"] is True

    def test_narrowing_is_not_widening(self, repo: LayersRepo) -> None:
        repo.edit("service", BAD_SERVICE)
        repo.write(
            "pyproject.toml",
            PYPROJECT.replace(
                'prefixes = ["service"]\nimports = ["kernel"]',
                'prefixes = ["service"]\nimports = ["kernel", "cli"]',
            ),
        )
        repo.adopt()
        repo.commit_as_origin_main()
        repo.write("pyproject.toml", PYPROJECT)
        code, out = repo.run("--check")
        assert "widened" not in out
        assert code == 1

    def test_flag_needs_check_or_update(self, repo: LayersRepo) -> None:
        with pytest.raises(SystemExit):
            repo.run("--json", "--allow-config-change")


class TestDynamicImports:
    """Only importlib's own helpers count, in every spelling they can take."""

    @pytest.mark.parametrize(
        "text",
        [
            'import importlib\nimportlib.import_module(name="app.service")\n',
            'from importlib import import_module\nimport_module(name="app.service")\n',
            '__import__(name="app.service")\n',
            'import importlib\nimportlib.import_module(".service", package="app")\n',
            'import importlib\nimportlib.import_module(".service", "app")\n',
            'from importlib import import_module as load\nload("app.service")\n',
            'import importlib as il\nil.import_module("app.service")\n',
            'import importlib.util\nimportlib.import_module("app.service")\n',
        ],
    )
    def test_recognised_forms_are_edges(self, tmp_path: Path, text: str) -> None:
        assert _violation(tmp_path, text)

    @pytest.mark.parametrize(
        "text",
        [
            'import importlib\nimportlib.import_module(".service")\n',
            'import importlib\nimportlib.import_module(".service", package=name)\n',
        ],
    )
    def test_unresolvable_calls_are_not_edges(self, tmp_path: Path, text: str) -> None:
        assert not _violation(tmp_path, text)


class TestUnrelatedCallsAreFalsePositives:
    """Any call named import_module is an edge: over-approximation by design."""

    @pytest.mark.parametrize(
        "text",
        [
            'loader.import_module("app.service")\n',
            'class A:\n    def go(self):\n        self.import_module("app.service")\n',
            'def import_module(name): ...\nimport_module("app.service")\n',
        ],
    )
    def test_calls_with_the_helper_name_are_edges(
        self, tmp_path: Path, text: str
    ) -> None:
        assert _violation(tmp_path, text)


class TestReexportInventory:
    """Any import in a package __init__ is an export, wherever it sits."""

    def _exports(self, tmp_path: Path, init: str) -> bool:
        return _violation(
            tmp_path,
            "from app import thing\n",
            **{"__init__.py": init},
        )

    def test_aliased_import_of_a_module_is_an_export(self, tmp_path: Path) -> None:
        assert self._exports(tmp_path, "import app.service as thing\n")

    def test_from_import_is_an_export(self, tmp_path: Path) -> None:
        assert self._exports(tmp_path, "from .service import thing\n")

    def test_function_local_import_still_counts(self, tmp_path: Path) -> None:
        init = "def lazy():\n    from .service import thing\n"
        assert self._exports(tmp_path, init)

    def test_later_rebinding_does_not_end_the_export(self, tmp_path: Path) -> None:
        assert self._exports(tmp_path, "from .service import thing\nthing = 1\n")

    def test_conditional_module_scope_import_is_an_export(self, tmp_path: Path) -> None:
        init = "try:\n    from .service import thing\nexcept ImportError:\n    pass\n"
        assert self._exports(tmp_path, init)


class TestReportWording:
    """The report says unassigned modules fail the check."""

    def test_unassigned_modules_are_not_called_exempt(self, tmp_path: Path) -> None:
        pkg = _package(tmp_path, {"kernel.py": "", "stray.py": ""})
        text = "\n".join(LayersReport(LayerScan(pkg)).render())
        assert "Unassigned modules: 1 (each fails --check)" in text
        assert "exempt" not in text
