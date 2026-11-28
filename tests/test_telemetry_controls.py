"""Consumer tests for oo-ratchet's usage-capture controls (TEL-3, 5, 6, 7, 9; PY-LOG-8).

Each test drives the real ``oo-ratchet`` entry point in a child process with a
scratch ``HOME`` and a scratch repository, so the answer is what the installed
command does, not what a function would do.
"""

from __future__ import annotations

import os
import re
import sqlite3
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from punt_observe.telemetry import (
    DurationAttr,
    EnumAttr,
    SchemaRegistry,
    TelemetryConfig,
    open_telemetry,
)

from oo_ratchet.__main__ import Dispatcher
from oo_ratchet.telemetry_settings import TelemetrySettings
from oo_ratchet.usage import Usage
from tests.conftest import GitSandbox

_TIMEOUT_S = 120
_DAY_NS = 86_400 * 1_000_000_000
_SRC = Path(__file__).resolve().parents[1] / "src"


def _db(home: Path) -> Path:
    return home / ".punt-labs" / "oo-ratchet" / "telemetry.db"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@pytest.fixture
def repo(tmp_path_factory: pytest.TempPathFactory) -> GitSandbox:
    """Return a committed repository whose ``pyproject.toml`` the tests rewrite."""
    box = GitSandbox(tmp_path_factory.mktemp("repo"))
    box.write("pkg/__init__.py", "from __future__ import annotations\n")
    box.write("pyproject.toml", "")
    box.commit("init")
    return box


def _run(
    home: Path, repo: GitSandbox, *, config: str = "", **env: str
) -> subprocess.CompletedProcess[str]:
    repo.write("pyproject.toml", config)
    return subprocess.run(
        [sys.executable, "-m", "oo_ratchet", "suppressions", "pkg"],
        cwd=repo.root,
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(home), **env},
        timeout=_TIMEOUT_S,
        check=False,
    )


def _count(home: Path) -> int:
    conn = sqlite3.connect(_db(home))
    try:
        return int(conn.execute("SELECT COUNT(*) FROM spans").fetchone()[0])
    finally:
        conn.close()


# TEL-9: every off switch wins, and nothing is opened while off.


@pytest.mark.parametrize(
    "config",
    [
        "[tool.oo-ratchet]\ntelemetry = false\n",
        "[tool.oo-ratchet]\ntelemetry = 'off'\n",
    ],
)
def test_config_switch_disables_capture_and_opens_no_store(
    private_home: Path, repo: GitSandbox, config: str
) -> None:
    result = _run(private_home, repo, config=config)

    assert result.returncode == 0, result.stderr
    assert not _db(private_home).exists()
    assert not list(_db(private_home).parent.glob("telemetry.db*"))


def test_config_on_still_captures_and_each_environment_switch_overrides_it(
    private_home: Path, repo: GitSandbox
) -> None:
    on = "[tool.oo-ratchet]\ntelemetry = true\n"

    assert _run(private_home, repo, config=on).returncode == 0
    assert _count(private_home) == 1
    _db(private_home).unlink()
    for switch in ("PUNT_TELEMETRY", "OO_RATCHET_TELEMETRY"):
        assert _run(private_home, repo, config=on, **{switch: "off"}).returncode == 0
        assert not _db(private_home).exists(), switch


def test_unreadable_settings_turn_capture_off_and_say_so(
    private_home: Path, repo: GitSandbox
) -> None:
    _run(private_home, repo, config="[tool.oo-ratchet\n")

    assert not _db(private_home).exists()
    log = private_home / ".punt-labs" / "oo-ratchet" / "logs" / "oo-ratchet.log"
    assert "capture is off" in log.read_text("utf-8")


def test_disabled_capture_starts_no_worker_thread() -> None:
    before = {t.name for t in threading.enumerate()}
    usage = Usage(["oo"])

    usage.start(TelemetryConfig(enabled=False))
    assert usage.run("oo", lambda: 0) == 0
    usage.stop()

    assert {t.name for t in threading.enumerate()} <= before


# TEL-7: 90 days by default, configurable, never unlimited, pruned at startup.


def test_default_retention_is_ninety_days(tmp_path: Path) -> None:
    assert TelemetryConfig().retention_days == 90
    assert TelemetrySettings(tmp_path).config().retention_days == 90


@pytest.mark.parametrize("days", ["0", "3651", "'forever'", "1.5", "true"])
def test_out_of_range_retention_keeps_the_default(tmp_path: Path, days: str) -> None:
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.oo-ratchet]\ntelemetry-retention-days = {days}\n"
    )

    assert TelemetrySettings(tmp_path).config().retention_days == 90


def test_expired_rows_are_pruned_on_the_next_run(
    private_home: Path, repo: GitSandbox
) -> None:
    _run(private_home, repo)
    now = time.time_ns()
    conn = sqlite3.connect(_db(private_home))
    conn.execute("UPDATE spans SET end_ns = ?", (now - 91 * _DAY_NS,))
    conn.commit()
    conn.close()

    _run(private_home, repo)

    assert _count(private_home) == 1  # the 91-day-old row is gone, today's stays


def test_configured_retention_prunes_sooner(
    private_home: Path, repo: GitSandbox
) -> None:
    config = "[tool.oo-ratchet]\ntelemetry-retention-days = 7\n"
    _run(private_home, repo, config=config)
    _run(private_home, repo, config=config)
    now = time.time_ns()
    conn = sqlite3.connect(_db(private_home))
    conn.execute("UPDATE spans SET end_ns = ? WHERE rowid = 1", (now - 10 * _DAY_NS,))
    conn.execute("UPDATE spans SET end_ns = ? WHERE rowid = 2", (now - 3 * _DAY_NS,))
    conn.commit()
    conn.close()

    _run(private_home, repo, config=config)

    conn = sqlite3.connect(_db(private_home))
    ages = conn.execute("SELECT end_ns FROM spans ORDER BY rowid").fetchall()
    conn.close()
    assert len(ages) == 2  # the 10-day row is gone; the 3-day and new rows stay
    assert min(age for (age,) in ages) < now - 2 * _DAY_NS


# TEL-3, TEL-4: the schema is an allowlist of two typed attributes.


def test_every_gate_declares_only_a_closed_outcome_and_a_duration() -> None:
    for schema in Usage(Dispatcher.GATES).schemas:
        assert set(schema.attributes) == {"outcome", "duration_ms"}, schema.name
        assert isinstance(schema.attributes["outcome"], EnumAttr)
        assert isinstance(schema.attributes["duration_ms"], DurationAttr)
        assert set(schema.attributes["outcome"].values) == {
            "pass",
            "fail",
            "invalid",
            "error",
        }
        assert re.fullmatch(r"oo-ratchet\.cli\.[a-z]+", schema.name)


def test_an_unknown_attribute_drops_the_event_and_never_fails_the_run(
    private_home: Path,
) -> None:
    schemas = Usage(["oo"]).schemas
    telemetry = open_telemetry("oo-ratchet", schemas, TelemetryConfig())

    telemetry.event("oo-ratchet.cli.oo", 1, outcome="pass", path="/home/someone/secret")
    telemetry.shutdown(timeout_s=2.0)

    assert _count(private_home) == 0
    rejected = SchemaRegistry(schemas).validate(
        "oo-ratchet.cli.oo", 1, {"outcome": "pass", "path": "x"}
    )
    assert not isinstance(rejected, dict)


# TEL-5, TEL-6, PY-LOG-3: private store, sidecars, no identifiers, no salt.


def test_existing_loose_store_and_sidecars_are_tightened(
    private_home: Path, repo: GitSandbox
) -> None:
    _run(private_home, repo)
    store = _db(private_home)
    sidecars = [store.with_name(store.name + s) for s in ("-wal", "-shm")]
    for path in (store, *sidecars):
        path.touch(exist_ok=True)
        path.chmod(0o644)
    store.parent.chmod(0o755)

    assert _run(private_home, repo).returncode == 0

    assert _mode(store.parent) == 0o700
    for path in (store, *(p for p in sidecars if p.exists())):
        assert _mode(path) == 0o600, path.name


def test_oo_ratchet_derives_no_identifier_so_creates_no_salt(
    private_home: Path, repo: GitSandbox
) -> None:
    _run(private_home, repo)

    assert not list((private_home / ".punt-labs").rglob("*salt*"))


# PY-LOG-1: the two pipelines are separate and instrumentation names no exporter.


def test_log_and_store_do_not_carry_each_others_records(
    private_home: Path, repo: GitSandbox
) -> None:
    _run(private_home, repo)

    log = private_home / ".punt-labs" / "oo-ratchet" / "logs" / "oo-ratchet.log"
    assert "Running suppressions gate" not in _db(private_home).read_bytes().decode(
        "utf-8", "replace"
    )
    assert "span" not in log.read_text("utf-8").lower()
    assert log.parent != _db(private_home).parent


def test_source_imports_no_exporter_and_no_telemetry_table_writer() -> None:
    banned = re.compile(
        r"^\s*(?:import|from)\s+(?:sqlite3|opentelemetry|"
        r"punt_observe\.telemetry\.(?:sqlite_exporter|otlp|providers))",
        re.MULTILINE,
    )
    offenders = [
        str(path.relative_to(_SRC))
        for path in sorted(_SRC.rglob("*.py"))
        if banned.search(path.read_text("utf-8"))
    ]

    assert offenders == []


# PY-LOG-3: denied permission changes surface at startup, never silently.


def test_a_log_that_cannot_be_secured_stops_the_run_with_a_clear_error(
    private_home: Path, repo: GitSandbox, tmp_path: Path
) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("keep")
    victim.chmod(0o644)
    logs = private_home / ".punt-labs" / "oo-ratchet" / "logs"
    logs.mkdir(parents=True)
    (logs / "oo-ratchet.log.1").symlink_to(victim)  # a backup slot redirected

    result = _run(private_home, repo)

    assert result.returncode == 2
    assert "cannot open the diagnostic log" in result.stderr
    assert _mode(victim) == 0o644  # the symlink was refused, not followed
    assert not _db(private_home).exists()


def test_loose_existing_log_files_and_directories_are_tightened(
    private_home: Path, repo: GitSandbox
) -> None:
    logs = private_home / ".punt-labs" / "oo-ratchet" / "logs"
    logs.mkdir(parents=True)
    logs.chmod(0o755)
    for name in ("oo-ratchet.log", "oo-ratchet.log.1", "oo-ratchet.log.5"):
        (logs / name).write_text("2026-01-01 00:00:00 [INFO] old: kept\n")
        (logs / name).chmod(0o644)

    assert _run(private_home, repo).returncode == 0

    assert _mode(logs) == 0o700
    for name in ("oo-ratchet.log", "oo-ratchet.log.1", "oo-ratchet.log.5"):
        assert _mode(logs / name) == 0o600, name
