"""The ports: what the operations need from the outside world."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from oo_ratchet.core.domain.changes import Diff
from oo_ratchet.core.domain.records import AuditRecord
from oo_ratchet.core.domain.scores import Measurement, Rows


class History(Protocol):
    """The repository's past: the base, and the state recorded at it."""

    def resolve(self, ref: str | None) -> str | None:
        """Return the comparison base: ``ref``, else the merge base of main."""
        ...

    def baseline_at(self, ref: str) -> Rows | None:
        """Return the baseline committed at ``ref``, ``None`` if absent."""
        ...

    def audit_at(self, ref: str) -> tuple[AuditRecord, ...] | None:
        """Return the audit records committed at ``ref``, ``None`` if absent."""
        ...

    def changes_since(self, base: str) -> Diff:
        """Return the files changed from ``base`` to the work tree."""
        ...

    def head(self) -> str | None:
        """Return the abbreviated HEAD commit, ``None`` outside a repo."""
        ...


class BaselineStore(Protocol):
    """The in-tree baseline: rows of metric values per file."""

    def exists(self) -> bool:
        """Return whether a baseline is present."""
        ...

    def rows(self) -> Rows:
        """Return the recorded rows."""
        ...

    def save(self, rows: Rows) -> None:
        """Replace the recorded rows."""
        ...


class AuditSink(Protocol):
    """The append-only decision trail."""

    def append(self, record: AuditRecord) -> None:
        """Add one record."""
        ...

    def records(self) -> tuple[AuditRecord, ...]:
        """Return every record, oldest first."""
        ...


class SourceReader(Protocol):
    """The work tree: what a scan finds in it."""

    def measure(self) -> Measurement:
        """Score every file of the selection."""
        ...

    def exists(self, path: str) -> bool:
        """Return whether ``path`` is on disk."""
        ...

    def key(self, requested: str) -> str:
        """Return the scored-file key a caller's spelling of a path names."""
        ...


class ArchiveRepo(Protocol):
    """The Git operations needed to materialize a historical source selection."""

    @property
    def root(self) -> Path | None: ...

    def archive_paths(self, ref: str, paths: Sequence[str], dest: Path) -> None: ...

    def _git(self, args: list[str]) -> str | None: ...
