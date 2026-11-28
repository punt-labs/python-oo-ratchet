"""Concurrent oo-ratchet processes roll the shared log over without losing a record.

``punt-observe`` owns rotation (LOG-10, LOG-11) and has its own multi-process
tests in its repository (``tests/test_logging.py``: ``test_multiprocess_rotation``
and ``test_concurrent_rotation_never_exceeds_cap``). This is the consumer test
the Python rules ask for: several real processes configure logging through
oo-ratchet's own ``DiagnosticLog`` and write past the 5 MiB threshold together.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from pathlib import Path

_WRITERS = 4
_RECORDS = 1_800  # per writer
_PAYLOAD = 800  # bytes of message per record; 4 * 1800 * ~860 B > 5 MiB
_MAX_BYTES = 5_242_880
_BACKUPS = 5
_TIMEOUT_S = 240

_WRITER = """
import logging, sys
from oo_ratchet.logging_config import DiagnosticLog

DiagnosticLog().configure()
log = logging.getLogger("oo_ratchet.rollover")
writer, count, size = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
for n in range(count):
    log.info("rec-%s-%05d %s END", writer, n, "x" * size)
"""

_RECORD = re.compile(
    r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d \[INFO\] oo_ratchet\.rollover: "
    r"rec-(\d+)-(\d{5}) x{800} END$"
)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_concurrent_writers_roll_the_log_over_intact_and_private(
    private_home: Path,
) -> None:
    env = {**os.environ, "HOME": str(private_home)}
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _WRITER, str(w), str(_RECORDS), str(_PAYLOAD)],
            env=env,
            stderr=subprocess.PIPE,
            text=True,
        )
        for w in range(_WRITERS)
    ]
    for proc in procs:
        _, stderr = proc.communicate(timeout=_TIMEOUT_S)
        assert proc.returncode == 0, stderr

    logs = private_home / ".punt-labs" / "oo-ratchet" / "logs"
    files = sorted(p for p in logs.iterdir() if p.name.startswith("oo-ratchet.log"))
    backups = [p for p in files if re.search(r"\.log\.\d+$", p.name)]
    assert backups, "the writers never crossed the rollover threshold"
    assert len(backups) <= _BACKUPS
    assert _mode(logs) == 0o700
    seen: list[tuple[str, str]] = []
    for path in [*files, *logs.glob("*.lock")]:
        assert _mode(path) == 0o600, path.name
    for path in files:
        if path.name.endswith(".lock"):
            continue
        assert path.stat().st_size <= _MAX_BYTES, path.name
        for line in path.read_text("utf-8").splitlines():
            match = _RECORD.match(line)
            assert match, f"torn or foreign record in {path.name}: {line[:120]!r}"
            seen.append((match[1], match[2]))
    assert len(seen) == _WRITERS * _RECORDS  # no record lost
    assert len(seen) == len(set(seen))  # no record written twice
