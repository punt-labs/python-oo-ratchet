"""Relax, RebaselineFiles and Rebaseline: the audited ways to loosen a baseline."""

from __future__ import annotations

from dataclasses import dataclass, field

from oo_ratchet.core.domain.records import AuditRecord
from oo_ratchet.core.domain.scores import Rows
from oo_ratchet.core.domain.verdicts import Failure, Verdict

from .blessbase import BlessBase
from .operation import Operation
from .rowchanges import RowChanges

Deltas = dict[str, dict[str, list[float]]]


@dataclass(slots=True)
class Bless:
    """What a scoped bless granted: waived loosenings, gains, file classes."""

    waived: Deltas = field(default_factory=dict)
    gains: Deltas = field(default_factory=dict)
    regressed: set[str] = field(default_factory=set)
    improved: set[str] = field(default_factory=set)

    def record(
        self,
        path: str,
        waived: dict[str, list[float]],
        gains: dict[str, list[float]],
    ) -> None:
        """Record the loosenings and gains of ``path`` against its base row."""
        if waived:
            self.waived[path] = waived
            self.regressed.add(path)
        if gains:
            self.gains[path] = gains
            self.improved.add(path)


class Relax(Operation):
    """Write one file's current metrics even if looser, with a justification."""

    def run(self, path: str, *, justify: str, source: str | None) -> Verdict:
        """Record ``path``'s scores and a waiver for each metric they loosen."""
        if not justify.strip():
            return Verdict.refused("blank-justification")
        measured = self._source.measure()
        current = measured.metrics()
        entry = current.get(path)
        if entry is None:
            return Verdict.refused("not-scored", path)
        recorded = self._store.rows().get(path)
        if recorded is None:
            return Verdict.refused("no-row", path)
        loosened = self._policy.loosened(entry, recorded)
        if not loosened:
            return Verdict.refused("nothing-to-relax", path)
        rows = dict(self._store.rows())
        rows[path] = entry
        self._store.save(rows)
        self._audit.append(
            AuditRecord(
                verdict="relaxed",
                deltas={path: {m: [recorded[m], entry[m]] for m in loosened}},
                files_scored=len(current),
                files_regressed=1,
                source=source,
                commit=self._history.head(),
                reason=justify,
            )
        )
        return Verdict.ok(f"relaxed {path}", written=(path,))


class Rebaseline(Operation):
    """Reset the baseline unconditionally to the current scores."""

    def run(
        self, *, source: str | None, reason: str = "", detail: bool = False
    ) -> Verdict:
        """Replace every row; the audit names the rows that left.

        With ``detail`` the audit also carries each changed metric as
        ``[old, new]``, the files that gained and the files that lost, and the
        stripped ``reason``.
        """
        current = self._source.measure().metrics()
        stored = self._store.rows()
        removed = stored.keys() - current.keys()
        changes = RowChanges(self._policy, stored if detail else current, current)
        self._store.save(current)
        self._audit.append(
            AuditRecord(
                verdict="rebaseline",
                deltas=changes.deltas,
                files_scored=len(current),
                files_improved=changes.gained,
                files_regressed=changes.lost,
                removed=tuple(sorted(removed)),
                reason=reason.strip() or None,
                source=source,
                commit=self._history.head(),
            )
        )
        return Verdict.ok("baseline reset", written=tuple(sorted(current)))


class RebaselineFiles(Operation):
    """Bless the named files: bounded, scoped, tool-computed and audited.

    A metric refuses the bless only when it fails its target AND is worse than
    the recorded row. Refusal is per file: a refused file is not written while
    every other named file that clears its gate is.
    """

    def run(
        self,
        paths: list[str],
        *,
        reason: str,
        source: str | None,
        base: BlessBase | None = None,
    ) -> Verdict:
        """Bless ``paths`` against the current scores.

        A file is judged against its in-tree row. With ``base`` it is judged
        against its row at the comparison base, and a renamed file's old row
        is dropped.
        """
        if not reason.strip():
            return Verdict.refused("blank-reason")
        current = self._source.measure().metrics()
        stored = self._store.rows()
        base = base or BlessBase(stored)
        accepted, refused = self._partition(paths, current, base)
        if accepted:
            self._write(accepted, current, (stored, base), (reason, source))
        failures = (Failure("refused", tuple(refused)),) if refused else ()
        return Verdict(failures=failures, written=tuple(accepted))

    def _partition(
        self,
        paths: list[str],
        current: Rows,
        base: BlessBase,
    ) -> tuple[list[str], list[str]]:
        """Split ``paths`` into those that clear the gate and refusal messages."""
        accepted: list[str] = []
        refused: list[str] = []
        for requested in paths:
            path = self._source.key(requested)
            entry = current.get(path, {})
            policy = self._policy.for_path(path)
            gated = policy.over_cap_and_regressed(entry, base.row(path))
            if path not in current:
                refused.append(f"{requested}: not found in scored tree")
            elif gated:
                refused.append(f"{requested}: {policy.refusal(entry, gated)}")
            elif path not in accepted:
                accepted.append(path)
        return accepted, refused

    def _write(
        self,
        accepted: list[str],
        current: Rows,
        recorded: tuple[Rows, BlessBase],
        meta: tuple[str, str | None],
    ) -> None:
        stored, base = recorded
        rows = dict(stored)
        bless = Bless()
        for path in accepted:
            self._classify(path, current[path], base.row(path), bless)
            base.forget_predecessor(rows, path)
            rows[path] = current[path]
        reason, source = meta
        self._audit.append(
            AuditRecord(
                verdict="rebaseline-files",
                deltas=bless.waived,
                files_scored=len(accepted),
                files_improved=len(bless.improved - bless.regressed),
                files_regressed=len(bless.regressed),
                reason=reason,
                source=source,
                commit=self._history.head(),
                extra={"improved": bless.gains},
            )
        )
        self._store.save(rows)

    def _classify(
        self,
        path: str,
        entry: dict[str, float],
        old: dict[str, float] | None,
        bless: Bless,
    ) -> None:
        if old is not None:
            bless.record(path, *self._policy.changes(entry, old))
