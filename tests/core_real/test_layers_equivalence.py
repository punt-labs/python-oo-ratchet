"""The layers gate on the shared core agrees with the live gate, on real git repos.

Each scenario builds a real repository and runs every step twice from the same
state: through the live gate (``oo_ratchet.layers.cli.main``) and through the
core's ``EdgeGate``. The exit code, stdout and the two state files must match
byte for byte (timestamps, commit hashes and the repository path masked). Each
step also states the exit code it expects, so two gates that agree on a wrong
answer still fail.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from oo_ratchet.core.adapters.edgegate import EdgeGate
from oo_ratchet.core.domain.errors import StateError
from oo_ratchet.design.layer_config import LayerConfigError
from oo_ratchet.layers.cli import Options, main
from oo_ratchet.layers.scan import LayerScan, LayersScanError
from oo_ratchet.source_set import SourceSet
from tests.layers_repo import (
    BAD_KERNEL,
    BAD_SERVICE,
    PYPROJECT,
    LayersRepo,
)

pytestmark = pytest.mark.slow

STATE = (".oo-layers-baseline.json", ".oo-layers-audit.jsonl")
STAMP = re.compile(r'("ts":)"[^"]*"')
HASH = re.compile(r"\b[0-9a-f]{7,40}\b")
WIDE = PYPROJECT.replace('imports = ["kernel"]', 'imports = ["kernel", "cli"]', 1)
FIXED = '[tool.oo-ratchet.layers]\nentry = ["app.cli"]\ndomain = ["app.domain"]\n'
NEW_PACKAGE = "import app.kernel\n"


def run_new(argv: list[str]) -> int:
    """Run the check or update of ``argv`` through the core, as the CLI would."""
    opts = Options.parse(argv)
    if not SourceSet.path(opts.src).exists():
        sys.stdout.write(f"Not found: {opts.src}\n")
        return 1
    git = EdgeGate.repo(opts.src)
    root = git.root
    if root is None or not SourceSet(opts.src).inside(root):
        sys.stdout.write(f"FAIL: {opts.src} is not inside a git repository\n")
        return 1
    try:
        gate = EdgeGate(opts.src, LayerScan(opts.src), git)
        if opts.check:
            lines, code = gate.check(
                base_ref=opts.base_ref,
                require_base=opts.require_base,
                tripwire=opts.tripwire,
                allow_config_change=opts.allow_config_change,
            )
        else:
            lines, code = gate.update(
                allow_ci_write=opts.allow_ci_write,
                source=opts.source,
                config_change=opts.allow_config_change,
            )
    except (StateError, LayerConfigError, LayersScanError, OSError) as exc:
        lines, code = [f"FAIL: {exc}"], 1
    sys.stdout.writelines(line + "\n" for line in lines)
    return code


class Bench:
    """Run each step through both gates from the same repository state."""

    def __init__(self, repo: LayersRepo, capsys: pytest.CaptureFixture[str]) -> None:
        self.repo = repo
        self.capsys = capsys

    def step(self, *argv: str, code: int, on: Path | None = None) -> str:
        """Run ``argv`` through both gates, compare, and return the new stdout."""
        src = str(on or self.repo.root / "src" / "app")
        args = [src, *argv]
        before = self._files()
        old = self._run(main, args)
        old_state = self._state()
        self._put(before)
        new = self._run(run_new, args)
        assert new == old, f"core and live gate differ on {argv}"
        assert self._state() == old_state, f"state files differ on {argv}"
        assert new[0] == code, new[1]
        return new[1]

    def _run(self, runner: object, args: list[str]) -> tuple[int, str]:
        self.capsys.readouterr()
        try:
            status = runner(args)  # type: ignore[operator]
        except SystemExit as exc:
            status = int(exc.code or 0)
        raw = self.capsys.readouterr()
        return status, self._mask(raw.out + raw.err)

    def _mask(self, text: str) -> str:
        text = text.replace(str(self.repo.root), "<ROOT>")
        return HASH.sub("<SHA>", text)

    def _files(self) -> dict[str, bytes | None]:
        out: dict[str, bytes | None] = {}
        for name in STATE:
            path = self.repo.root / name
            out[name] = path.read_bytes() if path.exists() else None
        return out

    def _put(self, files: dict[str, bytes | None]) -> None:
        for name, data in files.items():
            path = self.repo.root / name
            if data is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(data)

    def _state(self) -> dict[str, str | None]:
        return {
            name: (
                None
                if data is None
                else self._mask(STAMP.sub(r'\1"T"', data.decode()))
            )
            for name, data in self._files().items()
        }


@pytest.fixture
def bench(repo: LayersRepo, capsys: pytest.CaptureFixture[str]) -> Bench:
    return Bench(repo, capsys)


class TestFirstAdoption:
    """No baseline anywhere: a violation fails, a clean tree passes, update adopts."""

    def test_violation_without_a_baseline_fails(self, bench: Bench) -> None:
        out = bench.step("--check", code=1)
        assert "app.kernel -> app.service" in out

    def test_clean_tree_without_a_baseline_passes(self, bench: Bench) -> None:
        bench.repo.edit("kernel", "")
        out = bench.step("--check", code=0)
        assert out.startswith("PASS: 4 modules scanned")

    def test_update_adopts_then_check_passes(self, bench: Bench) -> None:
        bench.step("--update", code=0)
        bench.repo.commit_as_origin_main()
        out = bench.step("--check", code=0)
        assert "1 baselined layer violations" in out

    def test_update_records_the_source(self, bench: Bench) -> None:
        bench.repo.commit_as_origin_main()
        bench.step("--update", "--source", "PR-7", code=0)


class TestChanges:
    """Regression, improvement and unchanged, against a committed base."""

    def test_new_violation_fails_check_and_update(self, bench: Bench) -> None:
        bench.repo.adopt()
        bench.repo.commit_as_origin_main()
        bench.repo.edit("service", BAD_SERVICE)
        assert "app.service -> app.cli" in bench.step("--check", code=1)
        bench.step("--update", code=1)

    def test_unchanged_tree_passes(self, bench: Bench) -> None:
        bench.repo.adopt()
        bench.repo.commit_as_origin_main()
        bench.step("--check", code=0)

    def test_fix_is_stale_until_update_then_passes(self, bench: Bench) -> None:
        bench.repo.adopt()
        bench.repo.commit_as_origin_main()
        bench.repo.edit("kernel", "")
        assert "no longer violate" in bench.step("--check", code=1)
        bench.step("--update", code=0)
        bench.step("--check", code=0)

    def test_baseline_hand_grown_past_the_base_fails(self, bench: Bench) -> None:
        bench.repo.adopt()
        bench.repo.commit_as_origin_main()
        bench.repo.edit("service", BAD_SERVICE)
        grown = {"app.kernel": ["app.service"], "app.service": ["app.cli"]}
        bench.repo.baseline.write_text(json.dumps(grown, indent=2))
        assert "did not" in bench.step("--check", code=1)

    def test_renamed_module_is_a_new_edge_and_a_stale_one(self, bench: Bench) -> None:
        bench.repo.adopt()
        bench.repo.commit_as_origin_main()
        bench.repo.edit("kernel", "")
        bench.repo.write("src/app/core.py", BAD_KERNEL)
        bench.step("--check", code=1)
        bench.step("--update", code=1)

    def test_check_names_the_base_with_an_explicit_ref(self, bench: Bench) -> None:
        sha = bench.repo.commit_as_origin_main()
        bench.step("--update", code=0)
        bench.repo.commit()
        bench.step("--check", "--base-ref", sha, code=0)


class TestBases:
    """Missing, stale and pre-adoption bases fail closed; adoption bootstraps."""

    def test_unresolvable_base_with_require_base_fails(self, bench: Bench) -> None:
        bench.repo.edit("kernel", "")
        bench.step("--check", "--require-base", code=1)

    def test_unresolvable_base_with_a_baseline_fails(self, bench: Bench) -> None:
        bench.step("--update", code=0)
        bench.step("--check", code=1)

    def test_bad_base_ref_fails(self, bench: Bench) -> None:
        bench.step("--update", code=0)
        bench.step("--check", "--base-ref", "nope", code=1)
        bench.step("--check", "--base-ref", "nope", "--require-base", code=1)

    def test_base_before_adoption_fails_when_main_has_the_baseline(
        self, bench: Bench
    ) -> None:
        old = bench.repo.commit_as_origin_main()
        bench.step("--update", code=0)
        bench.repo.commit_as_origin_main()
        bench.step("--check", "--base-ref", old, code=1)

    def test_base_before_adoption_passes_when_main_lacks_it(
        self, bench: Bench
    ) -> None:
        old = bench.repo.commit_as_origin_main()
        bench.step("--update", code=0)
        bench.step("--check", "--base-ref", old, code=0)

    def test_tripwire_bootstraps_the_adoption_commit(self, bench: Bench) -> None:
        old = bench.repo.commit_as_origin_main()
        bench.step("--update", code=0)
        bench.step("--check", "--base-ref", old, "--tripwire", code=0)

    def test_tripwire_without_a_baseline_fails(self, bench: Bench) -> None:
        old = bench.repo.commit_as_origin_main()
        bench.repo.edit("kernel", "")
        bench.step("--check", "--base-ref", old, "--tripwire", code=1)

    def test_tree_without_the_base_baseline_fails(self, bench: Bench) -> None:
        bench.step("--update", code=0)
        bench.repo.commit_as_origin_main()
        bench.repo.baseline.unlink()
        bench.step("--check", code=1)

    def test_new_package_at_the_base_is_adopted(self, bench: Bench) -> None:
        bench.repo.commit_as_origin_main()
        bench.repo.write("src/fresh/__init__.py", "")
        bench.repo.write("src/fresh/kernel.py", NEW_PACKAGE)
        bench.repo.write("src/fresh/service.py", "")
        bench.repo.write("src/fresh/cli.py", "")
        on = bench.repo.root / "src" / "fresh"
        bench.step("--check", code=1, on=on)
        bench.step("--update", code=0, on=on)


class TestPolicy:
    """A widened layer policy fails unless the change lands alone."""

    def test_widening_fails_and_can_be_accepted(self, bench: Bench) -> None:
        bench.repo.edit("kernel", "")
        bench.repo.adopt()
        bench.repo.commit_as_origin_main()
        bench.repo.write("pyproject.toml", WIDE)
        assert "widened" in bench.step("--check", code=1)
        bench.step("--check", "--allow-config-change", code=0)

    def test_declared_policy_missing_at_the_base_fails(self, bench: Bench) -> None:
        bench.repo.edit("kernel", "")
        bench.repo.commit_as_origin_main()
        bench.step("--update", code=0)
        bench.repo.write("pyproject.toml", WIDE)
        bench.step("--check", code=1)


class TestPurity:
    """Domain IO imports are edges; only --allow-config-change may add them."""

    def _fixed(self, bench: Bench, domain: str) -> None:
        repo = bench.repo
        repo.write("pyproject.toml", FIXED)
        repo.write("src/app/domain.py", domain)
        repo.write("src/app/cli.py", "import app.domain\n")
        (repo.root / "src/app/kernel.py").unlink()
        (repo.root / "src/app/service.py").unlink()

    def test_new_io_import_fails_and_is_refused_by_update(self, bench: Bench) -> None:
        self._fixed(bench, "X = 1\n")
        bench.repo.adopt()
        bench.repo.commit_as_origin_main()
        bench.repo.write("src/app/domain.py", "import subprocess\n")
        out = bench.step("--check", code=1)
        assert "domain purity" in out
        assert "domain purity" in bench.step("--update", code=1)

    def test_allow_config_change_accepts_the_io_edge(self, bench: Bench) -> None:
        self._fixed(bench, "X = 1\n")
        bench.repo.adopt()
        bench.repo.commit_as_origin_main()
        bench.repo.write("src/app/domain.py", "import subprocess\n")
        bench.step("--check", "--allow-config-change", code=1)
        bench.step("--update", "--allow-config-change", code=0)
        bench.repo.commit()
        bench.step("--check", "--allow-config-change", code=0)


class TestPackages:
    """The baseline file is shared; an update keeps other packages' rows."""

    def test_rows_of_other_packages_survive_and_dead_ones_retire(
        self, bench: Bench
    ) -> None:
        repo = bench.repo
        repo.write("src/other/__init__.py", "")
        repo.write("src/other/kernel.py", "")
        repo.edit("kernel", "")
        repo.write(
            ".oo-layers-baseline.json",
            '{"other.kernel": ["other.service"], "gone.a": ["gone.b"]}',
        )
        repo.commit_as_origin_main()
        bench.step("--update", code=0)
        bench.step("--check", code=0)


class TestRefusals:
    """Bad input, CI writes and corrupt state fail with a one-line message."""

    def test_missing_source_directory(self, bench: Bench) -> None:
        bench.step("--check", code=1, on=bench.repo.root / "nowhere")

    def test_source_outside_a_repository(
        self, bench: Bench, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        pkg = tmp_path_factory.mktemp("loose") / "app"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "a.py").write_text("")
        bench.step("--check", code=1, on=pkg)

    def test_missing_config(self, bench: Bench) -> None:
        bench.repo.write("pyproject.toml", "[tool.other]\n")
        bench.step("--check", code=1)
        bench.step("--update", code=1)

    def test_unassigned_module_is_refused(self, bench: Bench) -> None:
        bench.repo.write("src/app/stray.py", "")
        assert "unassigned module" in bench.step("--check", code=1)
        bench.step("--update", code=1)

    def test_ci_write_is_refused_without_the_flag(
        self, bench: Bench, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        bench.step("--update", code=1)
        bench.step("--update", "--allow-ci-write", code=0)

    def test_corrupt_in_tree_baseline(self, bench: Bench) -> None:
        bench.repo.baseline.write_text("{")
        bench.step("--check", code=1)
        bench.step("--update", code=1)

    def test_wrong_shape_in_tree_baseline(self, bench: Bench) -> None:
        bench.repo.baseline.write_text('{"a": "b"}')
        bench.step("--check", code=1)

    def test_corrupt_base_baseline(self, bench: Bench) -> None:
        bench.repo.baseline.write_text("{")
        bench.repo.commit_as_origin_main()
        bench.repo.baseline.write_text("{}")
        bench.step("--check", code=1)

    def test_relax_is_not_a_flag_of_this_gate(self, bench: Bench) -> None:
        bench.step("--relax", "app/kernel.py", code=2)

    def test_base_flags_need_check(self, bench: Bench) -> None:
        bench.step("--update", "--tripwire", code=2)
        bench.step("--allow-config-change", code=2)
