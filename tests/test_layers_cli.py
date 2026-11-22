"""The layers gate end to end: ``--check``, ``--update`` and the baseline file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Self

import pytest

from oo_ratchet.__main__ import main as dispatch
from oo_ratchet.layers.cli import main

if TYPE_CHECKING:
    from tests.conftest import GitSandbox

_PYPROJECT = """\
[tool.oo-ratchet.layers.kernel]
prefixes = ["kernel"]
imports = []

[tool.oo-ratchet.layers.service]
prefixes = ["service"]
imports = ["kernel"]

[tool.oo-ratchet.layers.cli]
prefixes = ["cli"]
imports = ["kernel", "service"]
"""
_OK_SERVICE = "import app.kernel\n"
_BAD_KERNEL = "import app.service\n"
_BAD_SERVICE = "import app.kernel\nimport app.cli\n"
_KERNEL_VIOLATION = "app.kernel -> app.service"
_SERVICE_VIOLATION = "app.service -> app.cli"


class _Repo:
    """A sandbox repository holding a small ``app`` package and its pyproject."""

    _sandbox: GitSandbox
    _out: pytest.CaptureFixture[str]

    def __new__(
        cls,
        sandbox: GitSandbox,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> Self:
        self = super().__new__(cls)
        self._sandbox = sandbox
        self._out = capsys
        monkeypatch.chdir(sandbox.root)
        sandbox.write("pyproject.toml", _PYPROJECT)
        sandbox.write("src/app/__init__.py", "")
        sandbox.write("src/app/kernel.py", _BAD_KERNEL)
        sandbox.write("src/app/service.py", _OK_SERVICE)
        sandbox.write("src/app/cli.py", "")
        return self

    @property
    def baseline(self) -> Path:
        """Return the baseline file path."""
        return self._sandbox.root / ".oo-layers-baseline.json"

    @property
    def audit(self) -> list[dict[str, object]]:
        """Return the parsed audit entries, oldest first."""
        path = self._sandbox.root / ".oo-layers-audit.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()]

    def edit(self, module: str, text: str) -> None:
        """Rewrite one module of the package."""
        self._sandbox.write(f"src/app/{module}.py", text)

    def commit_as_origin_main(self) -> None:
        """Commit everything and point ``origin/main`` at that commit."""
        sha = self._sandbox.commit("snapshot")
        self._sandbox.run_git("update-ref", "refs/remotes/origin/main", sha)

    def run(self, *args: str) -> tuple[int, str]:
        """Run the layers gate on the package; return its exit code and stdout."""
        self._out.readouterr()
        code = main([str(self._sandbox.root / "src" / "app"), *args])
        return code, self._out.readouterr().out

    def adopt(self) -> None:
        """Commit the violating tree as main, then write the first baseline."""
        self.commit_as_origin_main()
        assert self.run("--update")[0] == 0


@pytest.fixture
def repo(
    git_sandbox: GitSandbox,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> _Repo:
    """Return a repo whose ``app.kernel`` imports ``app.service`` (a violation)."""
    return _Repo(git_sandbox, capsys, monkeypatch)


class TestCheck:
    """``--check`` fails on a new violation or a stale entry, passes otherwise."""

    def test_violation_without_a_baseline_fails(self, repo: _Repo) -> None:
        code, out = repo.run("--check")
        assert code == 1
        assert _KERNEL_VIOLATION in out

    def test_baselined_violation_passes(self, repo: _Repo) -> None:
        repo.adopt()
        code, out = repo.run("--check")
        assert (code, "PASS" in out) == (0, True)

    def test_new_violation_fails(self, repo: _Repo) -> None:
        repo.adopt()
        repo.edit("service", _BAD_SERVICE)
        code, out = repo.run("--check")
        assert code == 1
        assert _SERVICE_VIOLATION in out
        assert _KERNEL_VIOLATION not in out

    def test_stale_baseline_entry_fails(self, repo: _Repo) -> None:
        repo.adopt()
        repo.edit("kernel", "")
        code, out = repo.run("--check")
        assert code == 1
        assert "no longer violate" in out
        assert _KERNEL_VIOLATION in out

    def test_baseline_grown_past_the_base_fails(self, repo: _Repo) -> None:
        repo.adopt()
        repo.commit_as_origin_main()
        repo.edit("service", _BAD_SERVICE)
        repo.baseline.write_text(
            json.dumps(
                {"app.kernel": ["app.service"], "app.service": ["app.cli"]}, indent=2
            )
        )
        code, out = repo.run("--check")
        assert code == 1
        assert "did not" in out
        assert _SERVICE_VIOLATION in out

    def test_missing_config_fails(self, repo: _Repo) -> None:
        (repo.baseline.parent / "pyproject.toml").write_text("[tool.other]\n")
        code, out = repo.run("--check")
        assert code == 1
        assert "oo-ratchet.layers" in out


class TestUpdate:
    """``--update`` adopts a first baseline, then only shrinks it."""

    def test_first_update_adopts_and_audits(self, repo: _Repo) -> None:
        repo.adopt()
        assert json.loads(repo.baseline.read_text()) == {"app.kernel": ["app.service"]}
        (entry,) = repo.audit
        assert (entry["verdict"], entry["added"], entry["removed"]) == (
            "adopt",
            [_KERNEL_VIOLATION],
            [],
        )

    def test_update_after_a_fix_shrinks_the_baseline(self, repo: _Repo) -> None:
        repo.adopt()
        repo.edit("kernel", "")
        assert repo.run("--update")[0] == 0
        assert json.loads(repo.baseline.read_text()) == {}
        assert repo.audit[-1]["verdict"] == "pass"
        assert repo.audit[-1]["removed"] == [_KERNEL_VIOLATION]
        assert repo.run("--check")[0] == 0

    def test_update_refuses_a_new_violation(self, repo: _Repo) -> None:
        repo.adopt()
        before = repo.baseline.read_text()
        repo.edit("service", _BAD_SERVICE)
        code, out = repo.run("--update")
        assert code == 1
        assert _SERVICE_VIOLATION in out
        assert repo.baseline.read_text() == before
        assert len(repo.audit) == 1

    def test_update_is_refused_under_ci_without_the_flag(
        self, repo: _Repo, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        assert repo.run("--update")[0] == 1
        assert not repo.baseline.exists()
        assert repo.run("--update", "--allow-ci-write")[0] == 0


class TestViews:
    """Without an action the gate reports and never fails on violations."""

    def test_default_view_lists_violations(self, repo: _Repo) -> None:
        code, out = repo.run()
        assert code == 0
        assert "kernel -> service: 1" in out
        assert _KERNEL_VIOLATION in out

    def test_json_view(self, repo: _Repo) -> None:
        code, out = repo.run("--json")
        assert code == 0
        (violation,) = json.loads(out)["violations"]
        assert violation["source_layer"] == "kernel"

    def test_gate_is_registered_with_the_dispatcher(
        self, repo: _Repo, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo.run()
        assert dispatch(["layers", str(repo.baseline.parent / "src" / "app")]) == 0
        assert _KERNEL_VIOLATION in capsys.readouterr().out
