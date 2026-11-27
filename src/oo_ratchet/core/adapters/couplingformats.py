"""The coupling gate's audit line, as adopter repositories already hold it."""

from __future__ import annotations

import json

from oo_ratchet.core.domain.records import AuditRecord

from .formats import AuditFormat


class CouplingAuditFormat(AuditFormat):
    """One compact JSON object per line, as the coupling gate has always written.

    Unlike the shared line, ``reason`` is always present (``null`` when there
    is none), and ``removed`` is present only when it names a file.
    """

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
            "reason": record.reason,
            "deltas": record.deltas,
        }
        if record.removed:
            entry["removed"] = sorted(record.removed)
        entry.update(record.extra)
        return json.dumps(entry, separators=(",", ":")) + "\n"
