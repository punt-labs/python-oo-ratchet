"""Relax, RebaselineFiles and Rebaseline: the audited ways to loosen a baseline."""

from __future__ import annotations

from oo_ratchet.core.domain.records import AuditRecord
from oo_ratchet.core.domain.scores import Rows
from oo_ratchet.core.domain.verdicts import Failure, Verdict

from .operation import Operation

Deltas = dict[str, dict[str, list[float]]]


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
        loosened = [m for m in self._policy.regressed(entry, recorded) if m in recorded]
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

    def run(self, *, source: str | None) -> Verdict:
        """Replace every row; the audit names the rows that left."""
        current = self._source.measure().metrics()
        removed = self._store.rows().keys() - current.keys()
        self._store.save(current)
        self._audit.append(
            AuditRecord(
                verdict="rebaseline",
                files_scored=len(current),
                removed=tuple(sorted(removed)),
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

    def run(self, paths: list[str], *, reason: str, source: str | None) -> Verdict:
        """Bless ``paths`` against the current scores."""
        if not reason.strip():
            return Verdict.refused("blank-reason")
        current = self._source.measure().metrics()
        stored = self._store.rows()
        accepted: list[str] = []
        refused: list[str] = []
        for requested in paths:
            path = self._source.key(requested)
            if path not in current:
                refused.append(f"{requested}: not found in scored tree")
                continue
            gated = self._policy.over_cap_and_regressed(current[path], stored.get(path))
            if gated:
                refused.append(
                    f"{requested}: {', '.join(gated)} over cap and regressed"
                )
                continue
            accepted.append(path)
        if accepted:
            self._write(accepted, current, stored, reason, source)
        failures = (Failure("refused", tuple(refused)),) if refused else ()
        return Verdict(failures=failures, written=tuple(accepted))

    def _write(
        self,
        accepted: list[str],
        current: Rows,
        stored: Rows,
        reason: str,
        source: str | None,
    ) -> None:
        rows = dict(stored)
        waived: Deltas = {}
        gains: Deltas = {}
        regressed: set[str] = set()
        improved: set[str] = set()
        for path in accepted:
            entry, old = current[path], stored.get(path)
            if old is not None:
                self._classify(path, entry, old, waived, gains, regressed, improved)
            rows[path] = entry
        self._audit.append(
            AuditRecord(
                verdict="rebaseline-files",
                deltas=waived,
                files_scored=len(accepted),
                files_improved=len(improved - regressed),
                files_regressed=len(regressed),
                reason=reason,
                source=source,
                commit=self._history.head(),
                extra={"improved": gains},
            )
        )
        self._store.save(rows)

    def _classify(
        self,
        path: str,
        entry: dict[str, float],
        old: dict[str, float],
        waived: Deltas,
        gains: Deltas,
        regressed: set[str],
        improved: set[str],
    ) -> None:
        changed = [m for m in entry if m in old and entry[m] != old[m]]
        worse = {m for m in self._policy.regressed(entry, old) if m in old}
        for m in changed:
            if m in worse:
                waived.setdefault(path, {})[m] = [old[m], entry[m]]
                regressed.add(path)
            elif self._policy.strictly_better(m, entry[m], old[m]):
                gains.setdefault(path, {})[m] = [old[m], entry[m]]
                improved.add(path)
