"""The committed rows a scoped bless is judged against."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Self

from oo_ratchet.core.domain.scores import Rows
from oo_ratchet.core.domain.verdicts import Verdict

from .ports import History


@dataclass(frozen=True, slots=True)
class BlessBase:
    """The baseline at the comparison base, and the renames since it.

    A scoped bless judges a file by the row the next check will use: the row of
    the file at the base, or of the path it was renamed from.
    """

    rows: Rows = field(default_factory=dict)
    renames: dict[str, str] = field(default_factory=dict)

    def row(self, path: str) -> dict[str, float] | None:
        """Return the base row of ``path``, following a rename."""
        return self.rows.get(self.renames.get(path, path))

    def forget_predecessor(self, rows: Rows, path: str) -> None:
        """Drop from ``rows`` the path ``path`` was renamed from, if it was."""
        old = self.renames.get(path)
        if old is not None and old != path:
            rows.pop(old, None)

    @classmethod
    def load(
        cls, history: History, base_ref: str | None, *, require_base: bool
    ) -> Self | Verdict | None:
        """Return the base a bless compares with, or the refusal that stops it.

        An explicit ref that does not resolve, or no base under
        ``--require-base``, refuses. With no base at all (a local first
        adoption) there is none, and the in-tree rows stand in.
        """
        base = history.resolve(base_ref)
        if base is None:
            if base_ref is not None:
                return Verdict.refused("bless-bad-ref", base_ref)
            if require_base:
                return Verdict.refused("base-unresolvable")
            return None
        reference = history.baseline_at(base)
        if not reference and require_base:
            return Verdict.refused("bless-no-base-baseline")
        return cls(reference or {}, dict(history.changes_since(base).renames))
