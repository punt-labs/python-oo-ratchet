"""The audit record: one line of a gate's append-only decision trail."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import ClassVar

from .verdicts import Waiver

Deltas = Mapping[str, Mapping[str, list[float]]]


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """One audited verdict: what was scored, what moved, and why."""

    WAIVABLE: ClassVar[frozenset[str]] = frozenset({"relaxed", "rebaseline-files"})

    verdict: str
    deltas: Deltas = field(default_factory=dict)
    files_scored: int = 0
    files_improved: int = 0
    files_regressed: int = 0
    removed: tuple[str, ...] = ()
    reason: str | None = None
    source: str | None = None
    commit: str | None = None
    ts: str | None = None
    extra: Mapping[str, object] = field(default_factory=dict)

    def waivers(self) -> frozenset[Waiver]:
        """Return the (path, metric) pairs this record permits to loosen."""
        if self.verdict not in self.WAIVABLE:
            return frozenset()
        return frozenset(
            Waiver(path, metric)
            for path, metrics in self.deltas.items()
            for metric in metrics
        )

    @staticmethod
    def waivers_since(
        records: tuple[AuditRecord, ...], base: tuple[AuditRecord, ...] | None
    ) -> frozenset[Waiver]:
        """Return the waivers of records the base log does not already carry.

        A relaxation waives only the change that adds it; one already in the
        base log is history and waives nothing.
        """
        known = set(map(AuditRecord.key, base or ()))
        return frozenset(
            w for r in records if r.key() not in known for w in r.waivers()
        )

    def key(self) -> str:
        """Return an identity that ignores key order and formatting."""
        return repr(self._canon([(f, getattr(self, f)) for f in self.__slots__]))

    @classmethod
    def _canon(cls, value: object) -> object:
        if isinstance(value, Mapping):
            return tuple(sorted((str(k), cls._canon(v)) for k, v in value.items()))
        if isinstance(value, (list, tuple)):
            return tuple(cls._canon(v) for v in value)
        return value
