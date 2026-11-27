"""The ports of a gate that compares a total count, not per-file metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from oo_ratchet.core.domain.ledgers import Ledger
from oo_ratchet.core.domain.tallies import Tally, TallyRecord


class TallyHistory(Protocol):
    """The repository's past: the base, and the source counted at it."""

    def resolve(self, ref: str | None) -> str | None:
        """Return the comparison base: ``ref``, else the merge base of main."""
        ...

    def tally_at(self, ref: str) -> Tally | None:
        """Return a fresh count of the source as it was at ``ref``.

        ``None`` when the scanned source tree did not exist at ``ref``.
        """
        ...

    def adopted_at(self, ref: str) -> bool:
        """Return whether the scanned source tree exists at ``ref``."""
        ...

    def ledger_at(self, ref: str) -> Ledger | None:
        """Return the ceiling ledger committed at ``ref``, ``None`` if absent."""
        ...

    def head(self) -> str | None:
        """Return the abbreviated HEAD commit, ``None`` outside a repo."""
        ...


class TallyStore(Protocol):
    """The in-tree baseline: the counts last recorded."""

    @property
    def path(self) -> str:
        """Return where the baseline lives."""
        ...

    def exists(self) -> bool:
        """Return whether a baseline is present."""
        ...

    def total(self) -> int:
        """Return the recorded total, 0 when none is recorded."""
        ...

    def save(self, tally: Tally) -> None:
        """Replace the recorded counts."""
        ...


class LedgerStore(Protocol):
    """The in-tree ceiling ledger."""

    @property
    def path(self) -> str:
        """Return where the ledger lives."""
        ...

    def ledger(self) -> Ledger:
        """Return the recorded ceilings."""
        ...

    def add(self, file: str, ceiling: int, justify: str) -> None:
        """Record a ceiling for ``file``, replacing any earlier one."""
        ...


class TallyAudit(Protocol):
    """The append-only decision trail."""

    def append(self, record: TallyRecord) -> None:
        """Add one record."""
        ...


@dataclass(frozen=True, slots=True)
class TallyPorts:
    """The four ports a total-count gate's adapters fill."""

    history: TallyHistory
    store: TallyStore
    ledger: LedgerStore
    audit: TallyAudit
