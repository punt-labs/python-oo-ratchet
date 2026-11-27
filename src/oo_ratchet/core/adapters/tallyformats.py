"""The on-disk JSON formats of the total-count gate: baseline, ledger, audit."""

from __future__ import annotations

import json

from oo_ratchet.core.domain.errors import StateError
from oo_ratchet.core.domain.ledgers import Ceiling, Ledger
from oo_ratchet.core.domain.tallies import Tally, TallyRecord


class TallyFormat:
    """``{total, by_category, by_file, updated_at}``, two-space indented."""

    @staticmethod
    def decode(text: str, origin: str) -> dict[str, object]:
        """Parse a baseline, failing closed on anything that is not an object."""
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise StateError(
                f"unreadable suppression baseline file {origin}: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise StateError(f"non-dict suppression baseline file {origin}")
        return raw

    @staticmethod
    def total(entries: dict[str, object]) -> int:
        """Return the recorded total; anything that is not a number reads as 0.

        A bool is invalid data, not 1: coercing it would inflate the baseline.
        NaN and infinity cannot become an int and read as 0.
        """
        raw = entries.get("total", 0)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return 0
        try:
            return int(raw)
        except (ValueError, OverflowError):
            return 0

    @staticmethod
    def encode(tally: Tally, stamp: str) -> str:
        """Return the file text for ``tally``."""
        data = {
            "total": tally.total,
            "by_category": tally.by_category,
            "by_file": tally.by_file,
            "updated_at": stamp,
        }
        return json.dumps(data, indent=2) + "\n"


class LedgerFormat:
    """A JSON list of ``{file, ceiling, justify, added_at}``, sorted by file."""

    @classmethod
    def decode(cls, text: str, origin: str) -> Ledger:
        """Parse a ledger, failing closed on a malformed entry."""
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise StateError(
                f"unreadable suppression relax ledger {origin}: {exc}"
            ) from exc
        if not isinstance(raw, list):
            raise StateError(f"non-list suppression relax ledger {origin}")
        entries = [cls._entry(item, origin) for item in raw]
        return Ledger({e.file: e for e in entries})

    @staticmethod
    def _entry(item: object, origin: str) -> Ceiling:
        if not isinstance(item, dict):
            raise StateError(f"non-dict entry in suppression relax ledger {origin}")
        try:
            file = str(item["file"])
            ceiling = item["ceiling"]
            # A bool is an int subclass and 2.9 is not an integer: coercing
            # either would put an inexact ceiling in an audited ledger.
            if isinstance(ceiling, bool) or not isinstance(ceiling, int):
                raise StateError(f"non-integer ceiling for {file!r} in {origin}")
            entry = Ceiling(file, ceiling, str(item["justify"]), str(item["added_at"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise StateError(
                f"malformed entry in suppression relax ledger {origin}: {exc}"
            ) from exc
        if entry.ceiling <= 0:
            raise StateError(f"non-positive ceiling for {file!r} in {origin}")
        return entry

    @staticmethod
    def encode(ledger: Ledger) -> str:
        """Return the file text for ``ledger``."""
        data = [
            {
                "file": e.file,
                "ceiling": e.ceiling,
                "justify": e.justify,
                "added_at": e.added_at,
            }
            for e in ledger.ordered()
        ]
        return json.dumps(data, indent=2) + "\n"


class TallyAuditFormat:
    """One compact JSON object per line; its keys depend on the record's kind."""

    @staticmethod
    def encode(record: TallyRecord, stamp: str) -> str:
        """Return the line for ``record``, stamped ``stamp``, newline-terminated."""
        entry: dict[str, object] = {"ts": stamp}
        if record.kind == "update":
            entry |= {"total": record.total, "by_category": record.by_category}
        elif record.kind == "relaxed":
            entry |= {
                "verdict": "relaxed",
                "file": record.file,
                "before": record.before,
                "after": record.after,
                "reason": record.reason,
                "commit": record.commit,
            }
        else:
            entry |= {
                "verdict": record.kind,
                "before": record.before,
                "total": record.total,
                "by_category": record.by_category,
                "reason": record.reason,
                "source": record.source,
                "commit": record.commit,
            }
        return json.dumps(entry, separators=(",", ":")) + "\n"
