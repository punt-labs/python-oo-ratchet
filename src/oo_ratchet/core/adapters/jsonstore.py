"""The in-tree baseline file and the audit log file."""

from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Self

from oo_ratchet.core.domain.errors import StateError
from oo_ratchet.core.domain.records import AuditRecord
from oo_ratchet.core.domain.scores import Rows

from .formats import AuditFormat, BaselineFormat

logger = logging.getLogger(__name__)


class JsonBaselineStore:
    """Read and write a baseline JSON file; implements ``BaselineStore``."""

    _path: Path

    def __new__(cls, path: Path) -> Self:
        self = super().__new__(cls)
        self._path = path
        return self

    @property
    def path(self) -> Path:
        """Return the baseline file's path."""
        return self._path

    def exists(self) -> bool:
        """Return whether the file is present."""
        return self._path.exists()

    def rows(self) -> Rows:
        """Return the recorded rows, ``{}`` when there is no file."""
        if not self._path.exists():
            return {}
        try:
            text = self._path.read_text()
        except (OSError, UnicodeDecodeError) as exc:
            raise StateError(f"unreadable baseline file {self._path}: {exc}") from exc
        return BaselineFormat.decode(text, str(self._path))

    def save(self, rows: Rows) -> None:
        """Replace the file, sorted by path."""
        self._path.write_text(BaselineFormat.encode(rows))
        logger.info("Wrote baseline %s: %d files", self._path, len(rows))


class AuditFile:
    """Append to and read an audit log file; implements ``AuditSink``."""

    _path: Path
    _form: type[AuditFormat]

    def __new__(cls, path: Path, form: type[AuditFormat] = AuditFormat) -> Self:
        self = super().__new__(cls)
        self._path = path
        self._form = form
        return self

    @property
    def path(self) -> Path:
        """Return the audit log's path."""
        return self._path

    def append(self, record: AuditRecord) -> None:
        """Stamp ``record`` with the current time and add its line."""
        stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._path.open("a") as f:
            f.write(self._form.encode(record, stamp))
        logger.info("Appended %s entry to audit %s", record.verdict, self._path)

    def records(self) -> tuple[AuditRecord, ...]:
        """Return every record, oldest first; ``()`` when there is no file."""
        if not self._path.exists():
            return ()
        return AuditFormat.decode(self._path.read_text())
