"""What the shared redactor does to the paths and errors oo-ratchet logs.

The clauses are LOG-2, LOG-6 and LOG-14.

oo-ratchet logs the baseline and audit paths it writes. These tests pin what a
reader of the log file sees for them, so a change in ``punt-observe`` that
stopped masking a home directory or a URL credential fails here.
"""

from __future__ import annotations

import logging
from pathlib import Path

from oo_ratchet.logging_config import DiagnosticLog


def _written(home: Path, *emit: tuple[int, str, object]) -> str:
    path = DiagnosticLog().configure()
    log = logging.getLogger("oo_ratchet.redaction")
    for level, message, arg in emit:
        log.log(level, message, arg)
    for handler in logging.getLogger().handlers:
        handler.flush()
    return path.read_text("utf-8")


def test_the_home_directory_prefix_becomes_a_tilde(private_home: Path) -> None:
    text = _written(
        private_home,
        (logging.INFO, "Wrote baseline %s", f"{private_home}/proj/.oo-baseline.json"),
    )

    assert str(private_home) not in text
    assert "Wrote baseline ~/proj/.oo-baseline.json" in text


def test_a_path_outside_home_keeps_its_directory_names(private_home: Path) -> None:
    """Only the home prefix is masked: repository directory names stay visible."""
    text = _written(
        private_home,
        (logging.INFO, "Wrote baseline %s", "/srv/acme-project/.oo-baseline.json"),
    )

    assert "/srv/acme-project/.oo-baseline.json" in text


def test_url_credentials_and_path_are_masked_in_message_and_traceback(
    private_home: Path,
) -> None:
    path = DiagnosticLog().configure()
    log = logging.getLogger("oo_ratchet.redaction")
    try:
        raise ValueError(
            "fetch https://user:PASSWORD@host.example/org/private-repo.git"
        )
    except ValueError:
        log.exception("git failed: %s", "https://user:PASSWORD@host.example/org/x")
    for handler in logging.getLogger().handlers:
        handler.flush()

    text = path.read_text("utf-8")
    assert "PASSWORD" not in text
    assert "private-repo" not in text
    assert text.count("\n") == 1  # the traceback is escaped onto one physical line
