"""The on-disk JSON formats of a baseline and an audit log."""

from __future__ import annotations

import json
from typing import ClassVar

from oo_ratchet.core.domain.errors import StateError
from oo_ratchet.core.domain.records import AuditRecord
from oo_ratchet.core.domain.scores import Rows


class BaselineFormat:
    """``{path: {metric: number}}``, sorted by path, two-space indented."""

    @classmethod
    def decode(cls, text: str, origin: str) -> Rows:
        """Parse a baseline, failing closed on anything that could fail open.

        A non-dict row would make ``metric not in row`` a substring test, and a
        bool would compare as 0 or 1: both would skip a regression.
        """
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise StateError(f"unreadable baseline {origin}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise StateError(f"non-dict baseline {origin}")
        if not all(isinstance(v, dict) for v in loaded.values()):
            raise StateError(f"non-dict entry in baseline {origin}")
        if not all(
            isinstance(m, (int, float)) and not isinstance(m, bool)
            for row in loaded.values()
            for m in row.values()
        ):
            raise StateError(f"non-numeric metric in baseline {origin}")
        rows: Rows = loaded
        return rows

    @staticmethod
    def encode(rows: Rows) -> str:
        """Return the file text for ``rows``."""
        return json.dumps(dict(sorted(rows.items())), indent=2) + "\n"


class AuditFormat:
    """One compact JSON object per line, key order fixed."""

    HEAD: ClassVar[tuple[str, ...]] = (
        "ts",
        "commit",
        "source",
        "files_scored",
        "files_improved",
        "files_regressed",
        "verdict",
    )
    KNOWN: ClassVar[frozenset[str]] = frozenset({*HEAD, "reason", "deltas", "removed"})

    @classmethod
    def decode(cls, text: str | None) -> tuple[AuditRecord, ...]:
        """Parse every non-blank line, naming the bad line on failure."""
        return tuple(cls._line(ln) for ln in (text or "").splitlines() if ln.strip())

    @classmethod
    def _line(cls, line: str) -> AuditRecord:
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise StateError(f"malformed audit entry {line[:80]!r}: {exc}") from exc
        if not isinstance(raw, dict):
            raise StateError(f"malformed audit entry {line[:80]!r}: not an object")
        return AuditRecord(
            verdict=raw.get("verdict", ""),
            deltas=raw.get("deltas") or {},
            files_scored=raw.get("files_scored", 0),
            files_improved=raw.get("files_improved", 0),
            files_regressed=raw.get("files_regressed", 0),
            removed=tuple(raw.get("removed") or ()),
            reason=raw.get("reason"),
            source=raw.get("source"),
            commit=raw.get("commit"),
            ts=raw.get("ts"),
            extra={k: v for k, v in raw.items() if k not in cls.KNOWN},
        )

    @classmethod
    def encode(cls, record: AuditRecord, ts: str) -> str:
        """Return the line for ``record``, stamped ``ts``, newline-terminated."""
        entry: dict[str, object] = {
            "ts": ts,
            "commit": record.commit,
            "source": record.source,
            "files_scored": record.files_scored,
            "files_improved": record.files_improved,
            "files_regressed": record.files_regressed,
            "verdict": record.verdict,
        }
        if record.reason is not None:
            entry["reason"] = record.reason
        entry["deltas"] = record.deltas
        entry["removed"] = sorted(record.removed)
        entry.update(record.extra)
        return json.dumps(entry, separators=(",", ":")) + "\n"
