"""Configure oo-ratchet diagnostics for its command-line entry point.

Library modules only declare ``logging.getLogger(__name__)``; the
``oo-ratchet`` entry point calls :meth:`DiagnosticLog.configure` before it
runs a gate, which routes every record to the private, redacted, rotated file
the shared ``punt-observe`` package owns at
``~/.punt-labs/oo-ratchet/logs/oo-ratchet.log``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Self, final

from punt_observe.logging import LoggingSetupError, configure_logging

__all__ = ["TOOL", "DiagnosticLog", "LoggingSetupError"]

TOOL = "oo-ratchet"


@final
class DiagnosticLog:
    """The one place an oo-ratchet process configures its diagnostics."""

    _stderr_level: str
    __slots__ = ("_stderr_level",)

    def __new__(cls, stderr_level: str = "WARNING") -> Self:
        """Echo records at ``stderr_level`` or above to stderr."""
        self = super().__new__(cls)
        self._stderr_level = stderr_level
        return self

    def configure(self) -> Path:
        """Configure the private durable sink and terminal diagnostics.

        stdout is never a log sink: gate reports and ``--json`` output stay
        clean for the callers that parse them.

        Returns:
            The path of the active log file.

        Raises:
            LoggingSetupError: The home directory cannot be found, or the
                private log directory or file cannot be secured.
        """
        try:
            return configure_logging(TOOL, "cli", stderr_level=self._stderr_level)
        except RuntimeError as exc:  # Path.home(): no HOME and no passwd entry
            msg = "cannot locate the home directory"
            raise LoggingSetupError(msg) from exc
