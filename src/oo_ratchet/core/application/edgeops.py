"""Check and update for the layers gate: a baseline of edges that may only shrink."""

from __future__ import annotations

from typing import Self

from oo_ratchet.core.domain.edges import EdgeBook, EdgeRecord, EdgeReview, EdgeVerdict
from oo_ratchet.core.domain.layer_edges import Edge
from oo_ratchet.core.domain.policies import PolicyWidening
from oo_ratchet.core.domain.verdicts import Failure, Verdict

from .bases import Bases
from .edgeports import EdgePorts, Survey


class EdgeOperation:
    """An operation over the layers gate's ports, given the scan of the tree."""

    _ports: EdgePorts

    def __new__(cls, ports: EdgePorts) -> Self:
        self = super().__new__(cls)
        self._ports = ports
        return self

    @staticmethod
    def _refused(kind: str, *subjects: str) -> EdgeVerdict:
        return EdgeVerdict(Verdict.refused(kind, *subjects))


class EdgeCheck(EdgeOperation):
    """Compare a scan with the in-tree baseline, the base baseline and base config.

    Fails on a violating edge the baseline lacks, a baselined edge that no longer
    violates, a baseline that holds an edge the base did not, an edge that
    violates under the base's layer config, and a policy that widens imports.
    """

    def run(
        self,
        scan: Survey,
        *,
        base_ref: str | None,
        require_base: bool,
        tripwire: bool,
        allow_config_change: bool,
    ) -> EdgeVerdict:
        """Return the verdict for the change from the base to the work tree."""
        history, store = self._ports.history, self._ports.store
        bases = Bases(history, store)
        base = history.resolve(base_ref)
        allow = allow_config_change
        if base is None:
            first = bases.unresolved(require_base=require_base)
            if not first.passed:
                return EdgeVerdict(first)
            return self._review(scan, None, "", allow_config_change=allow)
        if not history.adopted_at(base):
            first = bases.undocumented(tripwire=tripwire)
            if not first.passed:
                return EdgeVerdict(first)
            return self._review(scan, None, base, allow_config_change=allow)
        if not store.exists():
            return self._refused("tree-no-baseline")
        at_base = history.edges_at(base)
        scoped = frozenset() if at_base is None else at_base.scoped(scan.package)
        adopting = not scoped and not history.has_package(base, scan.package)
        return self._review(
            scan,
            None if adopting else scoped,
            base,
            compare=True,
            allow_config_change=allow,
        )

    def _review(
        self,
        scan: Survey,
        base_edges: frozenset[Edge] | None,
        base: str,
        *,
        compare: bool = False,
        allow_config_change: bool,
    ) -> EdgeVerdict:
        history = self._ports.history
        accepted = scan.io_edges if allow_config_change else frozenset()
        config = None
        if compare:
            config = history.policy_at(
                base, scan.config_path, strict=base_edges is not None
            )
        under_base: list[Edge] = []
        widened: list[str] = []
        if config is not None:
            shared = history.shared_at(base, scan.modules, scan.package)
            if base_edges is not None:
                held = scan.under(config).edges - base_edges - accepted
                under_base = sorted(e for e in held if e.source in set(shared))
            if not allow_config_change:
                widened = PolicyWidening.found(scan.config, config, sorted(set(shared)))
        review = EdgeReview(
            scan.violations,
            self._ports.store.book().scoped(scan.package),
            len(scan.modules),
            len(scan.unassigned),
            base_edges,
            tuple(under_base),
            tuple(widened),
            accepted,
            scan.problems,
        )
        return EdgeVerdict(
            Verdict(failures=review.failures()),
            review=review,
            purity=scan.io_edges,
            base=base,
        )


class EdgeUpdate(EdgeOperation):
    """Write the scan's violations as the baseline; never add one.

    With no rows for the package yet, every current violation is adopted. With
    some, a violation they lack is refused and nothing is written.
    """

    def run(
        self, scan: Survey, *, source: str | None, config_change: bool
    ) -> EdgeVerdict:
        """Write the baseline and the audit entry, or refuse and write nothing.

        ``config_change`` lets the update add domain-purity edges, and only those.
        If the audit entry cannot be written the previous baseline is put back.
        """
        store = self._ports.store
        permitted = scan.io_edges if config_change else frozenset()
        refusal = self._refusal(scan, permitted)
        if refusal is not None:
            return refusal
        book = store.book()
        current = scan.edges
        recorded = book.scoped(scan.package)
        adopting = not recorded
        retired = book.rooted_in(self._dead(book, scan.package))
        before = store.snapshot()
        store.save(book.replaced(recorded | retired, current))
        record = EdgeRecord(
            "adopt" if adopting else "pass",
            len(scan.modules),
            len(current),
            current if adopting else (current & permitted) - recorded,
            recorded - current,
            self._ports.history.head(),
            source,
            config_change,
            retired,
        )
        try:
            self._ports.audit.append(record)
        except OSError:
            store.restore(before)
            raise
        return EdgeVerdict(Verdict.ok(written=(store.path,)), record=record)

    def _refusal(self, scan: Survey, permitted: frozenset[Edge]) -> EdgeVerdict | None:
        known = self._ports.store.book().scoped(scan.package)
        added = (
            [str(e) for e in sorted(scan.edges - known - permitted)] if known else []
        )
        refusals = (
            ("refuse-problems", list(scan.problems)),
            ("refuse-new", added),
        )
        for kind, rows in refusals:
            if rows:
                verdict = Verdict(failures=(Failure(kind, tuple(rows)),))
                return EdgeVerdict(verdict, purity=scan.io_edges)
        return None

    def _dead(self, book: EdgeBook, package: str) -> set[str]:
        """Return the roots of other packages whose directory no longer exists."""
        tree = self._ports.tree
        gone = book.foreign_roots(package)
        return {n for n in gone if n.isidentifier() and not tree.has_package(n)}
