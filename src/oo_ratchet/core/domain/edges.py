"""The layers gate's types: the edge book, one audited write and a check's review."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from typing import Self

from oo_ratchet.design.layer_edges import Edge, Violation

from .verdicts import Failure, Verdict


@dataclass(frozen=True, slots=True)
class EdgeBook:
    """The import edges allowed to stay in violation, across every package.

    The book is shared by the repository's packages; each operation reads and
    rewrites only the scanned package's rows.
    """

    edges: frozenset[Edge] = frozenset()

    def scoped(self, package: str) -> frozenset[Edge]:
        """Return the edges whose importing module is in ``package``."""
        return frozenset(e for e in self.edges if e.within(package))

    def foreign_roots(self, package: str) -> frozenset[str]:
        """Return the top-level names of the packages other rows belong to."""
        return frozenset(
            e.source.split(".")[0] for e in self.edges if not e.within(package)
        )

    def rooted_in(self, roots: Collection[str]) -> frozenset[Edge]:
        """Return the edges whose importing module is under one of ``roots``."""
        return frozenset(e for e in self.edges if e.source.split(".")[0] in roots)

    def replaced(self, drop: frozenset[Edge], add: frozenset[Edge]) -> Self:
        """Return the book without ``drop`` and with ``add``."""
        return type(self)((self.edges - drop) | add)


@dataclass(frozen=True, slots=True)
class EdgeRecord:
    """One audited baseline write: ``adopt`` a first baseline, or ``pass`` a shrink."""

    verdict: str
    modules: int
    violations: int
    added: frozenset[Edge]
    removed: frozenset[Edge]
    commit: str | None
    source: str | None
    config_change: bool = False
    retired: frozenset[Edge] = frozenset()


@dataclass(frozen=True, slots=True)
class EdgeReview:
    """Everything a check weighs: the scan, the baseline, the base and the policy."""

    violations: tuple[Violation, ...]
    recorded: frozenset[Edge]
    modules: int
    unassigned: int
    base_edges: frozenset[Edge] | None = None
    under_base: tuple[Edge, ...] = ()
    widened: tuple[str, ...] = ()
    accepted: frozenset[Edge] = frozenset()
    problems: tuple[str, ...] = ()

    @property
    def violating(self) -> int:
        """Return how many edges violate."""
        return len(self.violations)

    def failures(self) -> tuple[Failure, ...]:
        """Return one failure per way the scan fails, each naming its rows."""
        found = {v.edge: str(v) for v in self.violations}
        new = sorted(set(found) - self.recorded)
        sections = (
            ("new-violations", tuple(found[e] for e in new)),
            ("stale-entries", self._rows(self.recorded - set(found))),
            ("baseline-grown", self._rows(self._grown())),
            ("under-base", self._rows(e for e in self.under_base if e not in new)),
            ("policy-widened", self.widened),
            ("not-covered", self.problems),
        )
        return tuple(Failure(kind, rows) for kind, rows in sections if rows)

    def _grown(self) -> frozenset[Edge]:
        if self.base_edges is None:
            return frozenset()
        return self.recorded - self.base_edges - self.accepted

    @staticmethod
    def _rows(edges: Iterable[Edge]) -> tuple[str, ...]:
        return tuple(str(e) for e in sorted(edges))


@dataclass(frozen=True, slots=True)
class EdgeVerdict:
    """A verdict, with the review behind a check or the record of a write.

    ``purity`` is the scan's domain-purity edges, which the report points at;
    ``base`` is the commit a check compared with.
    """

    verdict: Verdict
    review: EdgeReview | None = None
    record: EdgeRecord | None = None
    purity: frozenset[Edge] = field(default_factory=frozenset)
    base: str = ""

    @property
    def passed(self) -> bool:
        """Return whether the operation succeeded."""
        return self.verdict.passed

    @property
    def failures(self) -> tuple[Failure, ...]:
        """Return the reasons the operation failed."""
        return self.verdict.failures
