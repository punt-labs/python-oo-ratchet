"""The layers gate end to end: ``--check``, ``--update`` and the baseline file."""

from __future__ import annotations

import json

import pytest

from oo_ratchet.__main__ import main as dispatch
from tests.layers_repo import (
    BAD_KERNEL,
    BAD_SERVICE,
    KERNEL_VIOLATION,
    OK_SERVICE,
    PYPROJECT,
    SERVICE_VIOLATION,
    LayersRepo,
)


class TestCheck:
    """``--check`` fails on a new violation or a stale entry, passes otherwise."""

    def test_violation_without_a_baseline_fails(self, repo: LayersRepo) -> None:
        code, out = repo.run("--check")
        assert code == 1
        assert KERNEL_VIOLATION in out

    def test_baselined_violation_passes(self, repo: LayersRepo) -> None:
        repo.adopt()
        code, out = repo.run("--check")
        assert (code, "PASS" in out) == (0, True)

    def test_new_violation_fails(self, repo: LayersRepo) -> None:
        repo.adopt()
        repo.edit("service", BAD_SERVICE)
        code, out = repo.run("--check")
        assert code == 1
        assert SERVICE_VIOLATION in out
        assert KERNEL_VIOLATION not in out

    def test_stale_baseline_entry_fails(self, repo: LayersRepo) -> None:
        repo.adopt()
        repo.edit("kernel", "")
        code, out = repo.run("--check")
        assert code == 1
        assert "no longer violate" in out
        assert KERNEL_VIOLATION in out

    def test_baseline_grown_past_the_base_fails(self, repo: LayersRepo) -> None:
        repo.adopt()
        repo.commit_as_origin_main()
        repo.edit("service", BAD_SERVICE)
        repo.baseline.write_text(
            json.dumps(
                {"app.kernel": ["app.service"], "app.service": ["app.cli"]}, indent=2
            )
        )
        code, out = repo.run("--check")
        assert code == 1
        assert "did not" in out
        assert SERVICE_VIOLATION in out

    def test_missing_config_fails(self, repo: LayersRepo) -> None:
        (repo.baseline.parent / "pyproject.toml").write_text("[tool.other]\n")
        code, out = repo.run("--check")
        assert code == 1
        assert "oo-ratchet.layers" in out


class TestUpdate:
    """``--update`` adopts a first baseline, then only shrinks it."""

    def test_first_update_adopts_and_audits(self, repo: LayersRepo) -> None:
        repo.adopt()
        assert json.loads(repo.baseline.read_text()) == {"app.kernel": ["app.service"]}
        (entry,) = repo.audit
        assert (entry["verdict"], entry["added"], entry["removed"]) == (
            "adopt",
            [KERNEL_VIOLATION],
            [],
        )

    def test_update_after_a_fix_shrinks_the_baseline(self, repo: LayersRepo) -> None:
        repo.adopt()
        repo.edit("kernel", "")
        assert repo.run("--update")[0] == 0
        assert json.loads(repo.baseline.read_text()) == {}
        assert repo.audit[-1]["verdict"] == "pass"
        assert repo.audit[-1]["removed"] == [KERNEL_VIOLATION]
        assert repo.run("--check")[0] == 0

    def test_update_refuses_a_new_violation(self, repo: LayersRepo) -> None:
        repo.adopt()
        before = repo.baseline.read_text()
        repo.edit("service", BAD_SERVICE)
        code, out = repo.run("--update")
        assert code == 1
        assert SERVICE_VIOLATION in out
        assert repo.baseline.read_text() == before
        assert len(repo.audit) == 1

    def test_update_is_refused_under_ci_without_the_flag(
        self, repo: LayersRepo, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        assert repo.run("--update")[0] == 1
        assert not repo.baseline.exists()
        assert repo.run("--update", "--allow-ci-write")[0] == 0


class TestViews:
    """Without an action the gate reports and never fails on violations."""

    def test_default_view_lists_violations(self, repo: LayersRepo) -> None:
        code, out = repo.run()
        assert code == 0
        assert "kernel -> service: 1" in out
        assert KERNEL_VIOLATION in out

    def test_json_view(self, repo: LayersRepo) -> None:
        code, out = repo.run("--json")
        assert code == 0
        (violation,) = json.loads(out)["violations"]
        assert violation["source_layer"] == "kernel"

    def test_gate_is_registered_with_the_dispatcher(
        self, repo: LayersRepo, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo.run()
        assert dispatch(["layers", str(repo.baseline.parent / "src" / "app")]) == 0
        assert KERNEL_VIOLATION in capsys.readouterr().out


class TestFailClosed:
    """A gate that cannot see the whole package must fail, not pass."""

    def test_unassigned_module_fails_check(self, repo: LayersRepo) -> None:
        repo.adopt()
        repo.edit("stray", "")
        code, out = repo.run("--check")
        assert code == 1
        assert "app.stray" in out

    def test_unassigned_module_refuses_update(self, repo: LayersRepo) -> None:
        repo.edit("stray", "")
        code, out = repo.run("--update")
        assert code == 1
        assert "app.stray" in out
        assert not repo.baseline.exists()

    def test_launderer_through_an_unassigned_module_fails(
        self, repo: LayersRepo
    ) -> None:
        repo.adopt()
        repo.edit("kernel", "import app.stray\n")
        repo.edit("stray", "import app.service\n")
        assert repo.run("--check")[0] == 1

    def test_misspelled_prefix_fails(self, repo: LayersRepo) -> None:
        repo.adopt()
        repo.write("pyproject.toml", PYPROJECT.replace('["service"]', '["servcie"]'))
        code, out = repo.run("--check")
        assert code == 1
        assert "app.service" in out

    def test_wrong_source_root_fails(self, repo: LayersRepo) -> None:
        repo.adopt()
        code, out = repo.run_on(repo.root / "src", "--check")
        assert code == 1
        assert "__init__" in out

    def test_pass_line_reports_scanned_and_unassigned_counts(
        self, repo: LayersRepo
    ) -> None:
        repo.adopt()
        out = repo.run("--check")[1]
        assert "4 modules scanned, 0 unassigned" in out


class TestConfigRatchet:
    """The layer config is compared with the one at the merge base."""

    def test_widening_imports_with_a_new_violation_fails(
        self, repo: LayersRepo
    ) -> None:
        repo.adopt()
        repo.commit_as_origin_main()
        repo.edit("service", BAD_SERVICE)
        repo.write(
            "pyproject.toml",
            PYPROJECT.replace(
                'prefixes = ["service"]\nimports = ["kernel"]',
                'prefixes = ["service"]\nimports = ["kernel", "cli"]',
            ),
        )
        code, out = repo.run("--check")
        assert code == 1
        assert "base config" in out
        assert SERVICE_VIOLATION in out

    def test_unchanged_config_still_passes(self, repo: LayersRepo) -> None:
        repo.adopt()
        repo.commit_as_origin_main()
        assert repo.run("--check")[0] == 0


class TestOptionsNeedCheck:
    """Base options mean nothing without ``--check`` and are refused."""

    @pytest.mark.parametrize(
        "flags",
        [
            ["--base-ref", "HEAD"],
            ["--require-base"],
            ["--tripwire"],
            ["--update", "--tripwire"],
            ["--json", "--base-ref", "HEAD"],
        ],
    )
    def test_refused_without_check(self, repo: LayersRepo, flags: list[str]) -> None:
        with pytest.raises(SystemExit) as exc:
            repo.run(*flags)
        assert exc.value.code == 2

    def test_accepted_with_check(self, repo: LayersRepo) -> None:
        repo.adopt()
        assert repo.run("--check", "--base-ref", "HEAD", "--require-base")[0] == 0


class TestBaseResolution:
    """Every way of not knowing the base fails closed, as the coupling gate does."""

    def test_require_base_with_no_base_fails(self, repo: LayersRepo) -> None:
        repo.commit()
        code, out = repo.run("--check", "--require-base")
        assert code == 1
        assert "--require-base" in out

    def test_no_base_with_an_in_tree_baseline_fails(self, repo: LayersRepo) -> None:
        repo.commit()
        repo.write(".oo-layers-baseline.json", '{"app.kernel": ["app.service"]}')
        code, out = repo.run("--check")
        assert code == 1
        assert "cannot resolve merge-base" in out

    def test_tripwire_passes_on_the_adoption_commit(self, repo: LayersRepo) -> None:
        before = repo.commit_as_origin_main()
        assert repo.run("--update")[0] == 0
        repo.commit_as_origin_main()
        code, _ = repo.run("--check", "--base-ref", before, "--tripwire")
        assert code == 0

    def test_tripwire_without_a_baseline_fails(self, repo: LayersRepo) -> None:
        before = repo.commit_as_origin_main()
        code, out = repo.run("--check", "--base-ref", before, "--tripwire")
        assert code == 1
        assert "--tripwire with no baseline" in out

    def test_origin_main_unresolvable_with_a_baseline_fails(
        self, repo: LayersRepo
    ) -> None:
        before = repo.commit()
        assert repo.run("--update")[0] == 0
        code, out = repo.run("--check", "--base-ref", before)
        assert code == 1
        assert "origin/main is unresolvable" in out

    def test_base_that_predates_adoption_fails(self, repo: LayersRepo) -> None:
        before = repo.commit()
        assert repo.run("--update")[0] == 0
        repo.commit_as_origin_main()
        code, out = repo.run("--check", "--base-ref", before)
        assert code == 1
        assert "predates baseline adoption" in out

    def test_corrupt_in_tree_baseline_fails(self, repo: LayersRepo) -> None:
        repo.write(".oo-layers-baseline.json", "not json")
        code, out = repo.run("--check")
        assert code == 1
        assert "unreadable layers baseline" in out


class TestBaseConfigLocation:
    """The base config is read from the same pyproject the scan used."""

    def _nested(self, repo: LayersRepo) -> None:
        repo.write("pyproject.toml", "[tool.other]\nx = 1\n")
        repo.write("sub/pyproject.toml", PYPROJECT)
        repo.write("sub/src/app/__init__.py", "")
        repo.write("sub/src/app/kernel.py", BAD_KERNEL)
        repo.write("sub/src/app/service.py", OK_SERVICE)
        repo.write("sub/src/app/cli.py", "")

    def test_nested_pyproject_is_ratcheted_against_its_base_config(
        self, repo: LayersRepo
    ) -> None:
        self._nested(repo)
        src = repo.root / "sub" / "src" / "app"
        repo.commit_as_origin_main()
        assert repo.run_on(src, "--update")[0] == 0
        repo.commit_as_origin_main()
        repo.write("sub/src/app/service.py", BAD_SERVICE)
        repo.write(
            "sub/pyproject.toml",
            PYPROJECT.replace(
                'prefixes = ["service"]\nimports = ["kernel"]',
                'prefixes = ["service"]\nimports = ["kernel", "cli"]',
            ),
        )
        code, out = repo.run_on(src, "--check")
        assert code == 1
        assert "base config" in out

    def test_baseline_present_but_base_config_missing_fails(
        self, repo: LayersRepo
    ) -> None:
        repo.write("pyproject.toml", "[tool.other]\nx = 1\n")
        repo.write(".oo-layers-baseline.json", '{"app.kernel": ["app.service"]}')
        repo.commit_as_origin_main()
        repo.write("pyproject.toml", PYPROJECT)
        code, out = repo.run("--check")
        assert code == 1
        assert "no layer config at the base" in out


class TestUnresolvableImports:
    """An import Python itself rejects is a failure, not a skipped edge."""

    def test_relative_import_above_the_package_fails_check(
        self, repo: LayersRepo
    ) -> None:
        extra = '\n[tool.oo-ratchet.layers.lib]\nprefixes = ["lib"]\nimports = []\n'
        repo.write("pyproject.toml", PYPROJECT + extra)
        repo.edit("kernel", "")
        repo.write("src/app/lib/__init__.py", "")
        repo.write("src/app/lib/paths.py", "from ...service import api\n")
        code, out = repo.run("--check")
        assert code == 1
        assert "unresolvable relative import" in out
        assert "paths.py:1" in out
