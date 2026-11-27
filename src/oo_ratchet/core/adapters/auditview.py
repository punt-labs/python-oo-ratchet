"""The audit history of a gate, as a table: the ``--log`` view."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Self

from oo_ratchet.core.domain.errors import StateError


class AuditView:
    """Render an audit log file for a person.

    ``label`` names the gate in the errors, which say what was corrupt.
    """

    _path: Path
    _label: str

    def __new__(cls, path: Path, label: str) -> Self:
        self = super().__new__(cls)
        self._path = path
        self._label = label
        return self

    def lines(self) -> list[str]:
        """Return the history, one row per entry, oldest first."""
        if not self._path.exists():
            return ["No audit log found"]
        try:
            text = self._path.read_text()
        except (OSError, UnicodeDecodeError) as exc:
            msg = f"unreadable {self._label} audit log {self._path}: {exc}"
            raise StateError(msg) from exc
        head = (
            f"\n{'Timestamp':<22} {'Commit':<10} {'Scored':>7} "
            f"{'Improved':>9} {'Regressed':>10} {'Verdict':>12}"
        )
        rows = [self._row(self._entry(raw)) for raw in text.splitlines() if raw.strip()]
        return [head, "-" * 74, *rows]

    def _entry(self, raw: str) -> dict[str, object]:
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError as exc:
            msg = f"corrupt {self._label} audit log {self._path}: {exc}"
            raise StateError(msg) from exc
        if not isinstance(entry, dict):
            msg = (
                f"corrupt {self._label} audit log {self._path}: entry is not an object"
            )
            raise StateError(msg)
        return entry

    @staticmethod
    def _row(entry: dict[str, object]) -> str:
        commit = entry.get("commit") or "?"
        return (
            f"{entry.get('ts', '?')!s:<22} {commit!s:<10} "
            f"{entry.get('files_scored', 0)!s:>7} "
            f"{entry.get('files_improved', 0)!s:>9} "
            f"{entry.get('files_regressed', 0)!s:>10} "
            f"{entry.get('verdict', '?')!s:>12}"
        )
