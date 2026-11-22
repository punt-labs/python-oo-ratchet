"""Consumer tests for oo-ratchet's punt-observe diagnostics and usage telemetry.

The shared package owns redaction, rotation and storage and tests them itself.
These tests prove oo-ratchet's side of the contract: the entry point configures
a private durable log, every gate run records one typed usage event, the off
switches stop capture without touching diagnostics, stdout stays the report
channel, and an exporter swap needs no change to the instrumentation.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, final

import pytest
from opentelemetry.sdk.metrics.export import (
    MetricExporter,
    MetricExportResult,
    MetricsData,
)
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from punt_observe.telemetry import SchemaRegistry, TelemetryConfig

from oo_ratchet.__main__ import Dispatcher, main
from oo_ratchet.logging_config import DiagnosticLog
from oo_ratchet.usage import SCHEMA_VERSION, Usage

if TYPE_CHECKING:
    from collections.abc import Sequence

    from opentelemetry.sdk.trace import ReadableSpan

_SRC = Path(__file__).resolve().parents[1] / "src"
_TIMEOUT_S = 120


def _log(home: Path) -> Path:
    return home / ".punt-labs" / "oo-ratchet" / "logs" / "oo-ratchet.log"


def _db(home: Path) -> Path:
    return home / ".punt-labs" / "oo-ratchet" / "telemetry.db"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _cli(home: Path, *args: str, **extra: str) -> subprocess.CompletedProcess[str]:
    """Run the real ``oo-ratchet`` entry point in a child process."""
    return subprocess.run(
        [sys.executable, "-m", "oo_ratchet", *args],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(home), **extra},
        timeout=_TIMEOUT_S,
        check=False,
    )


def _events(home: Path) -> list[tuple[str, dict[str, Any]]]:
    conn = sqlite3.connect(_db(home))
    try:
        rows = conn.execute("SELECT name, attributes FROM spans").fetchall()
    finally:
        conn.close()
    return [(str(name), json.loads(attrs)) for name, attrs in rows]


@pytest.fixture
def secret_src(tmp_path: Path) -> Path:
    """Return a source tree outside any git repository, with a telling name."""
    path = tmp_path / "secret-project-name"
    path.mkdir()
    (path / "module.py").write_text("VALUE = 1\n")
    return path


def test_cli_entry_point_writes_private_durable_log(
    private_home: Path, secret_src: Path
) -> None:
    result = _cli(private_home, "suppressions", str(secret_src))

    assert result.returncode == 0, result.stderr
    assert result.stdout.lstrip().startswith("Total suppressions:")
    assert "[INFO]" not in result.stdout
    log = _log(private_home)
    assert _mode(log.parent) == 0o700
    assert _mode(log) == 0o600
    text = log.read_text("utf-8")
    assert re.search(r"\[INFO\] \S+: Running suppressions gate", text)
    assert "Finished suppressions gate: pass" in text


def test_cli_usage_event_carries_only_typed_attributes(
    private_home: Path, secret_src: Path
) -> None:
    _cli(private_home, "coupling", str(secret_src))

    [(name, attrs)] = _events(private_home)
    assert name == "oo-ratchet.cli.coupling"
    assert set(attrs) == {"outcome", "duration_ms"}
    assert attrs["outcome"] == "pass"
    assert _mode(_db(private_home)) == 0o600
    assert "secret-project-name" not in _db(private_home).read_bytes().decode(
        "utf-8", "replace"
    )


@pytest.mark.parametrize("switch", ["PUNT_TELEMETRY", "OO_RATCHET_TELEMETRY"])
def test_off_switch_stops_capture_but_not_diagnostics(
    private_home: Path, secret_src: Path, switch: str
) -> None:
    result = _cli(private_home, "design", str(secret_src), **{switch: "off"})

    assert result.returncode == 0, result.stderr
    assert not _db(private_home).exists()
    assert "Finished design gate: pass" in _log(private_home).read_text("utf-8")


def test_invalid_gate_input_records_an_invalid_outcome(
    private_home: Path, tmp_path: Path
) -> None:
    result = _cli(private_home, "design", str(tmp_path / "missing"))

    assert result.returncode == 2
    [(_, attrs)] = _events(private_home)
    assert attrs["outcome"] == "invalid"
    assert "Finished design gate: invalid" in _log(private_home).read_text("utf-8")


def test_unknown_gate_configures_nothing(private_home: Path) -> None:
    assert main(["bogus"]) == 2
    assert not (private_home / ".punt-labs").exists()


def test_concurrent_cli_processes_share_one_intact_log(
    private_home: Path, secret_src: Path
) -> None:
    writers = 6
    procs = [
        subprocess.Popen(
            [sys.executable, "-m", "oo_ratchet", "suppressions", str(secret_src)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "HOME": str(private_home), "PYTHONFAULTHANDLER": "1"},
        )
        for _ in range(writers)
    ]
    for proc in procs:
        _, stderr = proc.communicate(timeout=_TIMEOUT_S)
        assert proc.returncode == 0, stderr

    lines = _log(private_home).read_text("utf-8").splitlines()
    finished = [line for line in lines if "Finished suppressions gate" in line]
    assert len(finished) == writers
    assert all(re.match(r"\d{4}-\d{2}-\d{2} ", line) for line in lines)
    assert len(_events(private_home)) == writers


def test_schemas_cover_every_gate() -> None:
    declared = Usage(Dispatcher.GATES).schemas

    assert {schema.name for schema in declared} == {
        f"oo-ratchet.cli.{gate}" for gate in Dispatcher.GATES
    }
    for schema in declared:
        assert schema.version == SCHEMA_VERSION
        assert schema.kind == "event"


@pytest.mark.parametrize(
    ("version", "attrs", "valid"),
    [
        (1, {"outcome": "pass", "duration_ms": 1.5}, True),
        (1, {"outcome": "error"}, True),
        (2, {"outcome": "pass"}, False),
        (1, {"path": "/home/user/src"}, False),
        (1, {"outcome": "report text"}, False),
        (1, {"duration_ms": "1"}, False),
    ],
)
def test_schema_validation_rejects_unknown_and_free_text(
    version: int, attrs: dict[str, object], *, valid: bool
) -> None:
    registry = SchemaRegistry(Usage(["oo"]).schemas)

    result = registry.validate("oo-ratchet.cli.oo", version, attrs)

    assert isinstance(result, dict) is valid


@final
class _CapturingMetricExporter(MetricExporter):
    """Accept metric batches without network or disk IO."""

    def export(
        self,
        metrics_data: MetricsData,
        timeout_millis: float = 10_000,
        **kwargs: object,
    ) -> MetricExportResult:
        return MetricExportResult.SUCCESS

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True

    def shutdown(self, timeout_millis: float = 30_000, **kwargs: object) -> None:
        return None


@final
class _FailingSpanExporter(SpanExporter):
    """An exporter whose every write fails, like a full disk or dead collector."""

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        raise OSError("disk full")


def _otlp(span_exporter: SpanExporter) -> TelemetryConfig:
    return TelemetryConfig(
        exporter="otlp",
        otlp_endpoint="http://unused.invalid",
        otlp_consent=True,
        exporter_factory=lambda _endpoint: (
            span_exporter,
            _CapturingMetricExporter(),
        ),
    )


def test_exporter_swap_needs_no_reinstrumentation(private_home: Path) -> None:
    captured = InMemorySpanExporter()
    usage = Usage(["oo"])
    usage.start(_otlp(captured))

    assert usage.run("oo", lambda: 1) == 1
    usage.stop()

    [span] = captured.get_finished_spans()
    assert span.name == "oo-ratchet.cli.oo"
    assert dict(span.attributes or {})["outcome"] == "fail"
    assert not _db(private_home).exists()


def test_exporter_failure_never_changes_the_result(private_home: Path) -> None:
    usage = Usage(["oo"])
    usage.start(_otlp(_FailingSpanExporter()))

    assert usage.run("oo", lambda: 0) == 0
    usage.stop()


def test_run_records_error_and_reraises(private_home: Path) -> None:
    captured = InMemorySpanExporter()
    usage = Usage(["oo"])
    usage.start(_otlp(captured))

    def boom() -> int:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        usage.run("oo", boom)
    usage.stop()

    [span] = captured.get_finished_spans()
    assert dict(span.attributes or {})["outcome"] == "error"
    assert "boom" not in json.dumps(dict(span.attributes or {}))


@pytest.mark.parametrize(
    ("args", "code", "outcome"),
    [(["--help"], 0, "pass"), (["--bogus-flag"], 2, "invalid")],
)
def test_argparse_exit_is_classified_by_its_code(
    private_home: Path, secret_src: Path, args: list[str], code: int, outcome: str
) -> None:
    result = _cli(private_home, "oo", str(secret_src), *args)

    assert result.returncode == code
    [(_, attrs)] = _events(private_home)
    assert attrs["outcome"] == outcome
    if outcome == "pass":
        assert not result.stderr


def test_unstarted_usage_opens_no_store(private_home: Path) -> None:
    usage = Usage(["oo"])

    assert usage.run("oo", lambda: 0) == 0
    usage.stop()

    assert not (private_home / ".punt-labs").exists()


def test_log_records_are_redacted_and_single_line(private_home: Path) -> None:
    path = DiagnosticLog().configure()

    logging.getLogger("oo_ratchet.test").warning(
        "git failed: %s", "https://u:SECRET@host/p?token=SECRET\nforged [INFO] x"
    )
    for handler in logging.getLogger().handlers:
        handler.flush()

    text = path.read_text("utf-8")
    assert "SECRET" not in text
    assert text.count("\n") == 1


def test_cli_exits_cleanly_when_home_cannot_be_found(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_home() -> Path:
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", staticmethod(no_home))

    assert main(["oo", "."]) == 2
    assert "cannot open the diagnostic log" in capsys.readouterr().err


def test_source_never_configures_logging_by_hand() -> None:
    banned = re.compile(
        r"basicConfig|RotatingFileHandler|(import|from) logging\.handlers"
    )
    offenders = [
        str(path.relative_to(_SRC))
        for path in sorted(_SRC.rglob("*.py"))
        if banned.search(path.read_text("utf-8"))
    ]

    assert offenders == []
