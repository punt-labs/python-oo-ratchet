"""Every refusal and failure of a gate leaves a diagnostic line (LOG-3, LOG-12, LOG-13).

State changes already log what they wrote (``Wrote baseline`` and ``Appended``
entries). These tests drive the real ``oo-ratchet`` entry point in a child
process with a scratch ``HOME`` and read the durable log it leaves, so the
refusals and failures that end a run are held to the same standard as the
successes: one line naming the reason, at a level that says whether the
caller can act on it, and never the content of a file.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import GitSandbox

_TIMEOUT_S = 120
_MODULE = "from __future__ import annotations\n\n\ndef f(a):\n    return a\n"
_NOISY = (
    "from __future__ import annotations\n\n\ndef f(a):  # noqa: E501\n    return a\n"
)


def _log(home: Path) -> str:
    path = home / ".punt-labs" / "oo-ratchet" / "logs" / "oo-ratchet.log"
    return path.read_text("utf-8")


def _records(home: Path, needle: str) -> list[str]:
    """Return every log line that contains ``needle``."""
    return [line for line in _log(home).splitlines() if needle in line]


def _run(
    home: Path,
    cwd: Path,
    *args: str,
    monkeypatch: pytest.MonkeyPatch,
    **env: str,
) -> subprocess.CompletedProcess[str]:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return subprocess.run(
        [sys.executable, "-m", "oo_ratchet", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(home), **env},
        timeout=_TIMEOUT_S,
        check=False,
    )


@pytest.fixture
def repo(tmp_path_factory: pytest.TempPathFactory) -> GitSandbox:
    """Return a committed repository with a one-module package ``pkg``."""
    box = GitSandbox(tmp_path_factory.mktemp("repo"))
    box.write("pkg/__init__.py", "from __future__ import annotations\n")
    box.write("pkg/m.py", _MODULE)
    box.commit("init")
    return box


def test_unresolvable_base_is_a_warning_naming_the_reason(
    private_home: Path, repo: GitSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run(
        private_home,
        repo.root,
        "oo",
        "pkg",
        "--check",
        "--base-ref",
        "deadbeef",
        "--require-base",
        monkeypatch=monkeypatch,
    )

    assert result.returncode == 1
    assert "[WARNING]" in _log(private_home)
    assert "refused: base-unresolvable" in _log(private_home)


def test_corrupt_baseline_is_a_warning_without_its_content(
    private_home: Path, repo: GitSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo.write(".oo-baseline.json", "{SECRET-CONTENT")

    result = _run(
        private_home, repo.root, "oo", "pkg", "--check", monkeypatch=monkeypatch
    )

    assert result.returncode == 1
    text = _log(private_home)
    assert "[WARNING]" in text
    assert "state unreadable" in text
    assert "SECRET-CONTENT" not in text


def test_regression_refusal_is_an_info_line_with_a_subject_count(
    private_home: Path, repo: GitSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    for gate in ("suppressions", "coupling"):
        update = _run(
            private_home, repo.root, gate, "pkg", "--update", monkeypatch=monkeypatch
        )
        assert update.returncode == 0, update.stdout
    base = repo.commit("baselines")
    repo.write("pkg/m.py", _NOISY)

    result = _run(
        private_home,
        repo.root,
        "suppressions",
        "pkg",
        "--check",
        "--base-ref",
        base,
        monkeypatch=monkeypatch,
    )

    assert result.returncode == 1, result.stdout
    (record,) = _records(private_home, "Operation refused")
    assert "[INFO]" in record
    assert "Operation refused: suppression-increase (0 subjects)" in record


def test_unexpected_failure_logs_an_error_with_the_traceback(
    private_home: Path, repo: GitSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.geteuid() == 0:
        pytest.skip("root ignores file permissions")
    repo.root.chmod(0o555)  # the baseline cannot be created

    try:
        result = _run(
            private_home, repo.root, "oo", "pkg", "--update", monkeypatch=monkeypatch
        )
    finally:
        repo.root.chmod(0o755)

    assert result.returncode != 0
    text = _log(private_home)
    assert "[ERROR]" in text
    assert "PermissionError" in text


def test_a_blessed_baseline_logs_what_was_written_not_why(
    private_home: Path, repo: GitSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run(
        private_home,
        repo.root,
        "oo",
        "pkg",
        "--update",
        monkeypatch=monkeypatch,
    )
    bless = _run(
        private_home,
        repo.root,
        "oo",
        "pkg",
        "--rebaseline-files",
        "pkg/m.py",
        "--reason",
        "SECRET-REASON",
        monkeypatch=monkeypatch,
    )

    assert result.returncode == bless.returncode == 0
    text = _log(private_home)
    assert "Wrote baseline" in text
    assert "Appended rebaseline-files entry to audit" in text
    assert "SECRET-REASON" not in text


def test_a_ci_blocked_oo_write_logs_one_warning_naming_the_kind(
    private_home: Path, repo: GitSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run(
        private_home,
        repo.root,
        "oo",
        "pkg",
        "--update",
        monkeypatch=monkeypatch,
        GITHUB_ACTIONS="true",
    )

    assert result.returncode == 1, result.stdout
    (record,) = _records(private_home, "Operation refused")
    assert "[WARNING]" in record
    assert "Operation refused: ci-write (0 subjects)" in record


def test_an_enforced_design_finding_logs_one_info_line_with_the_count(
    private_home: Path, repo: GitSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = repo.run_git("rev-parse", "HEAD").strip()
    repo.write("pkg/m.py", _MODULE + "x = 0\n" * 401)
    repo.commit("add a middle man")

    result = _run(
        private_home,
        repo.root,
        "design",
        "pkg",
        "--shadow-check",
        base,
        "--enforce",
        monkeypatch=monkeypatch,
    )

    assert result.returncode == 1, result.stderr
    (record,) = _records(private_home, "Design findings enforced")
    assert "[INFO]" in record
    assert "Design findings enforced: 1 added gate-capable" in record


def test_a_design_scan_error_logs_one_warning_without_the_message(
    private_home: Path, repo: GitSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run(
        private_home,
        repo.root,
        "design",
        "pkg",
        "--shadow-check",
        "SECRET-REF",
        monkeypatch=monkeypatch,
    )

    assert result.returncode == 2, result.stderr
    (record,) = _records(private_home, "Design scan failed")
    assert "[WARNING]" in record
    assert "GitError" in record
    assert "SECRET-REF" not in _log(private_home)
