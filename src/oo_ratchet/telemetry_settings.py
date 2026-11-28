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
from collections.abc import Iterator
from pathlib import Path
from typing import Self, final

from punt_observe.telemetry import TelemetryConfig

__all__ = ["TelemetrySettings"]

logger = logging.getLogger(__name__)

_OFF_VALUES = frozenset({"off", "0", "false", "no"})
_OFF_VARIABLES = ("PUNT_TELEMETRY", "OO_RATCHET_TELEMETRY")


def _env_off() -> bool:
    """Return whether an environment switch turns capture off."""
    return any(
        os.environ.get(name, "").strip().lower() in _OFF_VALUES
        for name in _OFF_VARIABLES
    )


def _flag(table: dict[str, object]) -> bool:
    """Return the ``telemetry`` key; a value that is not a boolean means off."""
    enabled = table.get("telemetry", True)
    if isinstance(enabled, bool):
        return enabled
    logger.warning("Ignoring non-boolean telemetry setting; capture is off")
    return False


def _section(tool: object) -> dict[str, object] | None:
    table = tool.get("oo-ratchet", {}) if isinstance(tool, dict) else {}
    return table if isinstance(table, dict) else None


def _read(file: Path) -> dict[str, object] | None:
    """Return ``[tool.oo-ratchet]`` of ``file``, ``None`` when it is unusable."""
    try:
        data = tomllib.loads(file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        logger.warning("Cannot read the telemetry settings; capture is off")
        return None
    return _section(data.get("tool", {}))


def _directories(start: Path) -> Iterator[Path]:
    """Yield ``start`` and its parents, ending at the repository root."""
    for directory in (start, *start.parents):
        yield directory
        if (directory / ".git").exists():
            return


def _nearest(start: Path) -> Path | None:
    """Return the nearest ``pyproject.toml`` from ``start`` up to the repository."""
    for directory in _directories(start):
        if (file := directory / "pyproject.toml").is_file():
            return file
    return None


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
        return TelemetryConfig(enabled=self._enabled())

    def _enabled(self) -> bool:
        if _env_off():
            return False
        table = self._table()
        return table is not None and _flag(table)

    def _table(self) -> dict[str, object] | None:
        """Return ``[tool.oo-ratchet]``, ``{}`` when absent, ``None`` when unusable."""
        try:
            file = _nearest(self._start)
        except OSError:
            logger.warning("Cannot search for the telemetry settings; capture is off")
            return None
        return {} if file is None else _read(file)
