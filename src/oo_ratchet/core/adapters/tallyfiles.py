"""The total-count gate's files: baseline, ceiling ledger and audit log."""

from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Self

from oo_ratchet.core.domain.errors import StateError
from oo_ratchet.core.domain.ledgers import Ceiling, Ledger
from oo_ratchet.core.domain.tallies import Tally, TallyRecord

from .tallyformats import LedgerFormat, TallyAuditFormat, TallyFormat

logger = logging.getLogger(__name__)


def _now(fmt: str) -> str:
    return datetime.datetime.now(datetime.UTC).strftime(fmt)


class JsonTallyStore:
    """Read and write the baseline file; implements ``TallyStore``.

    The file is read when the store is built: a corrupt file fails here.
    """

    _path: Path
    _entries: dict[str, object]

    def __new__(cls, path: Path) -> Self:
        self = super().__new__(cls)
        self._path = path
        self._entries = self._load()
        return self

    @property
    def path(self) -> str:
        """Return the baseline file's path."""
        return str(self._path)

    def exists(self) -> bool:
        """Return whether the file is present."""
        return self._path.exists()

    def total(self) -> int:
        """Return the recorded total, 0 when there is no file."""
        return TallyFormat.total(self._entries)

    def save(self, tally: Tally) -> None:
        """Replace the file with ``tally``'s counts."""
        text = TallyFormat.encode(tally, _now("%Y-%m-%dT%H:%M:%SZ"))
        self._path.write_text(text)
        logger.info("Wrote suppression baseline %s: %d total", self._path, tally.total)

    def _load(self) -> dict[str, object]:
        if not self._path.exists():
            return {}
        try:
            text = self._path.read_text()
        except (OSError, UnicodeDecodeError) as exc:
            msg = f"unreadable suppression baseline file {self._path}: {exc}"
            raise StateError(msg) from exc
        return TallyFormat.decode(text, str(self._path))


class JsonLedger:
    """Read and write the ceiling ledger file; implements ``LedgerStore``."""

    _path: Path
    _ledger: Ledger

    def __new__(cls, path: Path) -> Self:
        self = super().__new__(cls)
        self._path = path
        self._ledger = self._load()
        return self

    @property
    def path(self) -> str:
        """Return the ledger file's path."""
        return str(self._path)

    def ledger(self) -> Ledger:
        """Return the recorded ceilings."""
        return self._ledger

    def add(self, file: str, ceiling: int, justify: str) -> None:
        """Record a ceiling for ``file``, replacing any earlier entry."""
        stamp = _now("%Y-%m-%dT%H:%M:%S.%fZ")
        entry = Ceiling(file, ceiling, justify, stamp)
        self._ledger = Ledger({**self._ledger.entries, file: entry})
        self._path.write_text(LedgerFormat.encode(self._ledger))
        logger.info("Wrote suppression relaxations %s", self._path)

    def _load(self) -> Ledger:
        if not self._path.exists():
            return Ledger()
        try:
            text = self._path.read_text()
        except (OSError, UnicodeDecodeError) as exc:
            msg = f"unreadable suppression relax ledger {self._path}: {exc}"
            raise StateError(msg) from exc
        return LedgerFormat.decode(text, str(self._path))


class TallyAuditFile:
    """Append to the audit log; implements ``TallyAudit``."""

    _path: Path

    def __new__(cls, path: Path) -> Self:
        self = super().__new__(cls)
        self._path = path
        return self

    def append(self, record: TallyRecord) -> None:
        """Stamp ``record`` with the current time and add its line."""
        line = TallyAuditFormat.encode(record, _now("%Y-%m-%dT%H:%M:%SZ"))
        with self._path.open("a") as f:
            f.write(line)
        logger.info("Appended %s entry to suppression audit", record.kind)
