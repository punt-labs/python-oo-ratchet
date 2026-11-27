"""A scripted session against a real git repository, for the coupling gate.

A ``Play`` builds a repository step by step and runs the gate's CLI entry point
at chosen steps. It records, for every run, the exit code, the report lines and
the state files the run left behind, with the volatile parts (repository path,
commit hashes, timestamps) replaced. Two implementations that behave alike
leave equal transcripts.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    import pytest

Main = Callable[[list[str] | None], int]

STATE_FILES = (".oo-coupling-baseline.json", ".oo-coupling-audit.jsonl")

# One shared body so git detects a rename across a small metric change.
BODY = (
    "from __future__ import annotations\n\n"
    "# shared body line one, present in every variant for rename detection\n"
    "# shared body line two, present in every variant for rename detection\n"
    "# shared body line three, present in every variant for rename detection\n\n"
)
LOW = BODY + '__all__ = ["x"]\n\nx = 1\n'  # public_names 1
HIGH = BODY + '__all__ = ["x", "y"]\n\nx = 1\ny = 2\n'  # public_names 2
HIGHER = BODY + '__all__ = ["x", "y", "z"]\n\nx = 1\ny = 2\nz = 3\n'
BROKEN = "def oops(:\n    pass\n"
HEADER = "from __future__ import annotations\n\n"


class Play:
    """One repository, one gate entry point, one transcript."""

    _root: Path
    _main: Main
    _capsys: pytest.CaptureFixture[str]
    _monkeypatch: pytest.MonkeyPatch
    _steps: list[dict[str, Any]]

    def __new__(
        cls,
        root: Path,
        main: Main,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> Self:
        self = super().__new__(cls)
        self._root = root
        self._main = main
        self._capsys = capsys
        self._monkeypatch = monkeypatch
        self._steps = []
        root.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "Tester")
        self.git("config", "commit.gpgsign", "false")
        self._root = Path(self.git("rev-parse", "--show-toplevel").strip())
        monkeypatch.chdir(self._root)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        return self

    @property
    def root(self) -> Path:
        """Return the repository root."""
        return self._root

    @property
    def steps(self) -> list[dict[str, Any]]:
        """Return the recorded runs."""
        return self._steps

    def git(self, *args: str) -> str:
        """Run a git command in the repository."""
        out = subprocess.run(
            ["git", *args],
            cwd=self._root,
            check=True,
            capture_output=True,
            text=True,
        )
        return out.stdout

    def write(self, rel: str, text: str) -> Self:
        """Write a file, creating parents."""
        path = self._root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return self

    def remove(self, rel: str) -> Self:
        """Delete a tracked or untracked file."""
        (self._root / rel).unlink()
        return self

    def move(self, src: str, dst: str) -> Self:
        """Rename a file with ``git mv``."""
        (self._root / dst).parent.mkdir(parents=True, exist_ok=True)
        self.git("mv", src, dst)
        return self

    def commit(self, message: str = "c") -> Self:
        """Stage everything and commit."""
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self

    def tag(self, name: str) -> Self:
        """Tag HEAD, so a run can name the commit identically in every repo."""
        self.git("tag", "-f", name)
        return self

    def origin_main(self, ref: str = "HEAD") -> Self:
        """Point ``refs/remotes/origin/main`` at ``ref``."""
        self.git(
            "update-ref", "refs/remotes/origin/main", self.git("rev-parse", ref).strip()
        )
        return self

    def checkout_new(self, branch: str) -> Self:
        """Create and switch to a branch."""
        self.git("checkout", "-q", "-b", branch)
        return self

    def env(self, name: str, value: str) -> Self:
        """Set an environment variable for later runs."""
        self._monkeypatch.setenv(name, value)
        return self

    def chdir(self, rel: str) -> Self:
        """Run later commands from a subdirectory."""
        self._monkeypatch.chdir(self._root / rel)
        return self

    def seed(self, target: str = "pkg") -> Self:
        """Write the baseline for ``target`` without recording the run."""
        self._invoke([target, "--rebaseline", "--allow-ci-write", "--reason", "seed"])
        return self

    def setup(self, *argv: str) -> Self:
        """Run the gate without recording it."""
        self._invoke(list(argv))
        return self

    def run(self, *argv: str) -> Self:
        """Run the gate and record the result."""
        code, lines = self._invoke(list(argv))
        self._steps.append(
            {
                "argv": [a.replace(str(self._root), "<root>") for a in argv],
                "code": code,
                "out": lines,
                "state": self._state(),
            }
        )
        return self

    def _invoke(self, argv: list[str]) -> tuple[int | str, list[str]]:
        self._capsys.readouterr()
        try:
            code: int | str = self._main(argv)
        except SystemExit as exc:
            code = f"exit {exc.code}"
        out = self._capsys.readouterr().out.replace(str(self._root), "<root>")
        return code, [self._volatile(line) for line in out.splitlines()]

    @staticmethod
    def _volatile(line: str) -> str:
        """Replace the timestamps and short commit hashes a run printed."""
        line = re.sub(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", "<ts>", line)
        return re.sub(r"\b[0-9a-f]{7}\b", "<commit>", line)

    def _state(self) -> dict[str, Any]:
        state: dict[str, Any] = {}
        for name in STATE_FILES:
            path = self._root / name
            if not path.exists():
                state[name] = None
            elif name.endswith(".jsonl"):
                state[name] = [
                    self._audit_line(ln) for ln in path.read_text().splitlines()
                ]
            else:
                state[name] = path.read_text()
        return state

    @staticmethod
    def _audit_line(line: str) -> str:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            return line
        if not isinstance(entry, dict):
            return line
        entry["ts"] = "<ts>"
        if entry.get("commit") is not None:
            entry["commit"] = "<commit>"
        return json.dumps(entry, separators=(",", ":"))
