"""Shared fixtures: a real throwaway git repository for the ratchet tests."""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Self

import pytest

from tests.layers_repo import LayersRepo


class GitSandbox:
    """A throwaway git repository the ratchet tests drive end-to-end.

    The merge-base ratchets (``tools/oo_ratchet``, ``tools/coupling``,
    ``tools/suppression``) read the *base-commit* baseline blob via
    ``git show <base>:<file>``, so they can only be exercised faithfully against
    a real commit graph — a mocked ``GitRepo`` drifts from the code it stands in
    for (the recurring remote/local-divergence bug class). This sandbox commits
    real trees so the tests score against genuine base blobs.
    """

    _root: Path

    def __new__(cls, root: Path) -> Self:
        self = super().__new__(cls)
        self._root = root
        self._git("init", "-q")
        self._git("config", "user.email", "ratchet@test.local")
        self._git("config", "user.name", "Ratchet Test")
        self._git("config", "commit.gpgsign", "false")
        return self

    @property
    def root(self) -> Path:
        """Return the repository root directory."""
        return self._root

    def write(self, relpath: str, text: str) -> Path:
        """Write ``text`` to ``relpath`` under the repo, creating parents."""
        path = self._root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def commit(self, message: str) -> str:
        """Stage everything and commit, returning the full commit hash."""
        self._git("add", "-A")
        self._git("commit", "-q", "-m", message)
        return self._git("rev-parse", "HEAD").strip()

    def run_git(self, *args: str) -> str:
        """Run an arbitrary git command in the repo and return its stdout.

        Lets a test seed refs the ratchets read — e.g. an
        ``refs/remotes/origin/main`` pointer for the coupling adoption-tripwire
        path — without a real remote.
        """
        return self._git(*args)

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self._root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout


@pytest.fixture
def git_sandbox(tmp_path: Path) -> GitSandbox:
    """Return a fresh :class:`GitSandbox` rooted at ``tmp_path``."""
    return GitSandbox(tmp_path)


@pytest.fixture(autouse=True)
def private_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """Point ``HOME`` at a scratch directory and undo any entry-point logging.

    The ``oo-ratchet`` entry point configures diagnostics and opens usage
    capture under ``~/.punt-labs/oo-ratchet``; without this, every in-process
    dispatcher test would write the real log and telemetry store and leave the
    root logger pointed at it for the rest of the run.

    Yields:
        The scratch home directory.
    """
    home = tmp_path_factory.mktemp("home")  # never inside a test's repository
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("PUNT_TELEMETRY", raising=False)
    monkeypatch.delenv("OO_RATCHET_TELEMETRY", raising=False)
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield home
    for handler in root.handlers:
        if handler not in handlers:
            handler.close()
    root.handlers[:] = handlers
    root.setLevel(level)


@pytest.fixture
def repo(
    git_sandbox: GitSandbox,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> LayersRepo:
    """Return a repo whose ``app.kernel`` imports ``app.service`` (a violation)."""
    return LayersRepo(git_sandbox, capsys, monkeypatch)
