"""Record privacy-safe usage of each gate through ``punt-observe``.

Every gate run emits one ``oo-ratchet.cli.<gate>`` event, version 1, carrying
only a closed-enum outcome and the wall time. Paths, source text, baselines
and report lines never enter a signal. Capture is local SQLite under
``~/.punt-labs/oo-ratchet/`` by default and stops entirely under
``PUNT_TELEMETRY=off`` or ``OO_RATCHET_TELEMETRY=off``; the exporter is
configuration, so instrumentation here never names one.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from typing import Literal, Self, final

from punt_observe.telemetry import (
    DurationAttr,
    EnumAttr,
    SignalSchema,
    Telemetry,
    TelemetryConfig,
    open_telemetry,
)

from oo_ratchet.logging_config import TOOL

__all__ = ["SCHEMA_VERSION", "Usage"]

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
_SHUTDOWN_TIMEOUT_S = 2.0

type Outcome = Literal["pass", "fail", "invalid", "error"]

_OUTCOMES: tuple[Outcome, ...] = ("pass", "fail", "invalid", "error")
_BY_EXIT_CODE: dict[int, Outcome] = {0: "pass", 1: "fail", 2: "invalid"}


_SIGNAL_PREFIX = f"{TOOL}.cli."


def _outcome_of(code: object) -> Outcome:
    """Return the outcome of an exit code; anything unexpected is an error."""
    if code is None:
        return "pass"
    return _BY_EXIT_CODE.get(code, "error") if isinstance(code, int) else "error"


@final
class Usage:
    """Record one usage event per gate run.

    Disabled until the entry point calls :meth:`start`, so importing the
    package or calling a gate's ``main`` directly never opens a store.
    """

    _schemas: tuple[SignalSchema, ...]
    _telemetry: Telemetry
    __slots__ = ("_schemas", "_telemetry")

    def __new__(cls, gates: Iterable[str]) -> Self:
        """Declare one ``oo-ratchet.cli.<gate>`` event per gate, capture disabled."""
        self = super().__new__(cls)
        attributes: dict[str, EnumAttr | DurationAttr] = {
            "outcome": EnumAttr(_OUTCOMES),
            "duration_ms": DurationAttr(),
        }
        self._schemas = tuple(
            SignalSchema(_SIGNAL_PREFIX + gate, SCHEMA_VERSION, "event", attributes)
            for gate in gates
        )
        self._telemetry = open_telemetry(TOOL, (), TelemetryConfig(enabled=False))
        return self

    @property
    def schemas(self) -> tuple[SignalSchema, ...]:
        """Return the versioned event schema of every gate."""
        return self._schemas

    def start(self, config: TelemetryConfig | None = None) -> None:
        """Open capture for this process; the off switches always win."""
        self._telemetry = open_telemetry(
            TOOL, self._schemas, config if config is not None else TelemetryConfig()
        )

    def stop(self) -> None:
        """Stop capture, bounding the wait for the store to flush."""
        self._telemetry.shutdown(timeout_s=_SHUTDOWN_TIMEOUT_S)

    def run(self, gate: str, call: Callable[[], int]) -> int:
        """Run one gate, then log and record its outcome and duration.

        ``SystemExit`` (argparse's ``--help`` and usage errors) is classified
        by its exit code; any other exception propagates unchanged after
        recording an ``error`` outcome. Recording itself never raises.
        """
        outcome: Outcome = "error"
        started = time.monotonic()
        try:
            code = call()
        except SystemExit as exc:
            outcome = _outcome_of(exc.code)
            raise
        else:
            outcome = _outcome_of(code)
            return code
        finally:
            duration_ms = (time.monotonic() - started) * 1000
            log = logger.info if outcome in {"pass", "fail"} else logger.warning
            log("Finished %s gate: %s in %.0f ms", gate, outcome, duration_ms)
            self._telemetry.event(
                _SIGNAL_PREFIX + gate,
                SCHEMA_VERSION,
                outcome=outcome,
                duration_ms=duration_ms,
            )
