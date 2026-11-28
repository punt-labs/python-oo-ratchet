"""The per-project usage-capture switch in ``[tool.oo-ratchet]``.

``telemetry = false`` turns usage capture off for the project;
``telemetry-retention-days = N`` (1 to 3650) shortens or lengthens the 90-day
default. The environment switches ``PUNT_TELEMETRY=off`` and
``OO_RATCHET_TELEMETRY=off`` are applied by ``punt-observe`` on top of this,
and any off switch wins. A setting that cannot be read or is the wrong type
turns capture off rather than guess, and says so in the diagnostic log.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Self, final

from punt_observe.telemetry import TelemetryConfig

__all__ = ["TelemetrySettings"]

logger = logging.getLogger(__name__)

_RETENTION_DAYS = (1, 3650)


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
        table = self._table()
        if table is None:
            return TelemetryConfig(enabled=False)
        enabled = table.get("telemetry", True)
        if not isinstance(enabled, bool):
            logger.warning("Ignoring non-boolean telemetry setting; capture is off")
            return TelemetryConfig(enabled=False)
        return TelemetryConfig(enabled=enabled, **self._retention(table))

    def _retention(self, table: dict[str, object]) -> dict[str, int]:
        days = table.get("telemetry-retention-days")
        if days is None:
            return {}
        low, high = _RETENTION_DAYS
        if type(days) is int and low <= days <= high:
            return {"retention_days": days}
        logger.warning("Ignoring telemetry-retention-days outside %d..%d", low, high)
        return {}

    def _table(self) -> dict[str, object] | None:
        """Return ``[tool.oo-ratchet]``, ``{}`` when absent, ``None`` when unusable."""
        for parent in (self._start, *self._start.parents):
            if (file := parent / "pyproject.toml").is_file():
                return self._read(file)
            if (parent / ".git").exists():
                break
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
