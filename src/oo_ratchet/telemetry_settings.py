"""The per-project usage-capture switch in ``[tool.oo-ratchet]``.

``telemetry = false`` turns usage capture off for the project. Retention is
not a project setting: events carry no project key and the store is shared by
every repository on the machine, so retention stays the 90-day default.
Other keys of the table are not this class's and are ignored here. The
environment switches ``PUNT_TELEMETRY=off`` and
``OO_RATCHET_TELEMETRY=off`` are applied by ``punt-observe`` on top of this,
and any off switch wins. A setting that cannot be read or is the wrong type
turns capture off rather than guess, and says so in the diagnostic log.
An environment off switch is honoured before the filesystem is touched, and
no filesystem error ever escapes: telemetry never fails a tool.
"""

from __future__ import annotations

import logging
import os
import tomllib
from pathlib import Path
from typing import Self, final

from punt_observe.telemetry import TelemetryConfig

__all__ = ["TelemetrySettings"]

logger = logging.getLogger(__name__)

_OFF_VALUES = frozenset({"off", "0", "false", "no"})
_OFF_VARIABLES = ("PUNT_TELEMETRY", "OO_RATCHET_TELEMETRY")

@final
class TelemetrySettings:
    """Read the telemetry keys of the nearest ``pyproject.toml`` above a directory."""

    _start: Path
    __slots__ = ("_start",)

    def __new__(cls, start: Path) -> Self:
        """Search ``start`` and its parents, stopping at the repository root."""
        self = super().__new__(cls)
        self._start = start
        return self

    def config(self) -> TelemetryConfig:
        """Return the capture configuration these settings select."""
        if self._env_off():
            return TelemetryConfig(enabled=False)
        table = self._table()
        if table is None:
            return TelemetryConfig(enabled=False)
        enabled = table.get("telemetry", True)
        if not isinstance(enabled, bool):
            logger.warning("Ignoring non-boolean telemetry setting; capture is off")
            return TelemetryConfig(enabled=False)
        return TelemetryConfig(enabled=enabled)

    @staticmethod
    def _env_off() -> bool:
        return any(
            os.environ.get(name, "").strip().lower() in _OFF_VALUES
            for name in _OFF_VARIABLES
        )

    def _table(self) -> dict[str, object] | None:
        """Return ``[tool.oo-ratchet]``, ``{}`` when absent, ``None`` when unusable."""
        try:
            for parent in (self._start, *self._start.parents):
                if (file := parent / "pyproject.toml").is_file():
                    return self._read(file)
                if (parent / ".git").exists():
                    break
        except OSError:
            logger.warning("Cannot search for the telemetry settings; capture is off")
            return None
        return {}

    @staticmethod
    def _read(file: Path) -> dict[str, object] | None:
        try:
            data = tomllib.loads(file.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            logger.warning("Cannot read the telemetry settings; capture is off")
            return None
        tool = data.get("tool", {})
        table = tool.get("oo-ratchet", {}) if isinstance(tool, dict) else {}
        return table if isinstance(table, dict) else None
