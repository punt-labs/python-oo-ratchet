"""The layers gate's files: the in-tree baseline and the audit log."""

from __future__ import annotations

import datetime
import logging
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Self

from oo_ratchet.core.domain.edges import EdgeBook, EdgeRecord

from .edgeformats import EdgeAuditFormat, EdgeFormat

if sys.platform != "win32":
    import fcntl

logger = logging.getLogger(__name__)


class JsonEdgeStore:
    """Read and write the baseline file; implements ``EdgeStore``.

    The file is read when the store is built: a corrupt file fails here. A write
    replaces the file atomically (a sibling temp file, then a rename).
    """

    _path: Path
    _book: EdgeBook

    def __new__(cls, path: Path) -> Self:
        self = super().__new__(cls)
        self._path = path
        text = self.snapshot()
        self._book = EdgeBook() if text is None else EdgeFormat.decode(text, str(path))
        return self

    @property
    def path(self) -> str:
        """Return the baseline file's path."""
        return str(self._path)

    def exists(self) -> bool:
        """Return whether the file is present."""
        return self._path.exists()

    def book(self) -> EdgeBook:
        """Return the recorded edges."""
        return self._book

    def snapshot(self) -> str | None:
        """Return the file text, or ``None`` when there is no file."""
        return self._path.read_text() if self._path.exists() else None

    def save(self, book: EdgeBook) -> None:
        """Write ``book`` sorted by source and refresh the in-memory view."""
        self._write(EdgeFormat.encode(book))
        self._book = book
        logger.info("Wrote layers baseline %s: %d edges", self._path, len(book.edges))

    def restore(self, text: str | None) -> None:
        """Put back what ``snapshot`` returned, deleting the file if there was none."""
        if text is None:
            self._path.unlink(missing_ok=True)
            self._book = EdgeBook()
            return
        self._write(text)
        self._book = EdgeFormat.decode(text, str(self._path))

    def _write(self, text: str) -> None:
        mode = stat.S_IMODE(self._path.stat().st_mode) if self._path.exists() else 0o644
        fd, name = tempfile.mkstemp(dir=self._path.parent, prefix=self._path.name + ".")
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(text)
            Path(name).chmod(mode)
            Path(name).replace(self._path)
        except OSError:
            Path(name).unlink(missing_ok=True)
            raise


class EdgeAuditFile:
    """Append to the audit log under an exclusive lock; implements ``EdgeAudit``."""

    _path: Path

    def __new__(cls, path: Path) -> Self:
        self = super().__new__(cls)
        self._path = path
        return self

    def append(self, record: EdgeRecord) -> None:
        """Stamp ``record`` with the current time and add its line.

        The lock covers the write and, if it fails, the cut back to the size the
        file had when the lock was taken, so a concurrent update can neither be
        truncated away nor interleave with a partial record.
        """
        now = datetime.datetime.now(datetime.UTC)
        line = EdgeAuditFormat.encode(record, now.strftime("%Y-%m-%dT%H:%M:%SZ"))
        fd = os.open(self._path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            if sys.platform != "win32":
                fcntl.flock(fd, fcntl.LOCK_EX)
            before = os.fstat(fd).st_size
            try:
                pending = memoryview(line)
                while pending:
                    pending = pending[os.write(fd, pending) :]
            except OSError:
                os.ftruncate(fd, before)
                raise
        finally:
            os.close(fd)
        logger.info("Appended %s entry to layers audit %s", record.verdict, self._path)
