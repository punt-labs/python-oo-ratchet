"""A sandbox repository with a small ``app`` package for the layers gate tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Self

from oo_ratchet.layers.cli import main

if TYPE_CHECKING:
    import pytest

    from tests.conftest import GitSandbox

PYPROJECT = """\
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
OK_SERVICE = "import app.kernel\n"
BAD_KERNEL = "import app.service\n"
BAD_SERVICE = "import app.kernel\nimport app.cli\n"
KERNEL_VIOLATION = "app.kernel -> app.service"
SERVICE_VIOLATION = "app.service -> app.cli"


class LayersRepo:
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
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        sandbox.write("pyproject.toml", PYPROJECT)
        sandbox.write("src/app/__init__.py", "")
        sandbox.write("src/app/kernel.py", BAD_KERNEL)
        sandbox.write("src/app/service.py", OK_SERVICE)
        sandbox.write("src/app/cli.py", "")
        return self

    @property
    def root(self) -> Path:
        """Return the repository root."""
        return self._sandbox.root

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

    def commit(self) -> str:
        """Commit everything and return the commit hash."""
        return self._sandbox.commit("snapshot")

    def commit_as_origin_main(self) -> str:
        """Commit everything, point ``origin/main`` at it, return the hash."""
        sha = self.commit()
        self._sandbox.run_git("update-ref", "refs/remotes/origin/main", sha)
        return sha

    def write(self, relpath: str, text: str) -> None:
        """Write a file under the repository root."""
        self._sandbox.write(relpath, text)

    def run(self, *args: str) -> tuple[int, str]:
        """Run the layers gate on the package; return its exit code and stdout."""
        return self.run_on(self._sandbox.root / "src" / "app", *args)

    def run_on(self, src: Path, *args: str) -> tuple[int, str]:
        """Run the layers gate on ``src``; return its exit code and stdout."""
        self._out.readouterr()
        code = main([str(src), *args])
        return code, self._out.readouterr().out

    def adopt(self) -> None:
        """Commit the violating tree as main, then write the first baseline."""
        self.commit_as_origin_main()
        assert self.run("--update")[0] == 0
