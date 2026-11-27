"""The layers operations over in-memory ports: no git, no filesystem."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from oo_ratchet.core.application.edgeops import EdgeCheck, EdgeUpdate
from oo_ratchet.core.application.edgeports import EdgePorts
from oo_ratchet.core.domain.edges import EdgeBook, EdgeRecord, EdgeVerdict
from oo_ratchet.core.domain.verdicts import Failure
from oo_ratchet.design.layer_config import LayerConfig
from oo_ratchet.design.layer_edges import Edge, Violation

BASE = "base0"
KERNEL = Edge("app.kernel", "app.service")
SERVICE = Edge("app.service", "app.cli")
OTHER = Edge("other.a", "other.b")


@dataclass
class Scan:
    """A scan of package ``app`` with the given violating edges."""

    found: tuple[Edge, ...] = ()
    package: str = "app"
    modules: tuple[str, ...] = ("app", "app.kernel")
    io_edges: frozenset[Edge] = frozenset()
    unassigned: tuple[str, ...] = ()
    problems: tuple[str, ...] = ()
    config: LayerConfig = field(default_factory=lambda: LayerConfig({}))
    config_path: Path | None = None

    @property
    def violations(self) -> tuple[Violation, ...]:
        return tuple(Violation(e, "kernel", "service") for e in self.found)

    @property
    def edges(self) -> frozenset[Edge]:
        return frozenset(self.found)

    def under(self, config: LayerConfig) -> Scan:
        return self


@dataclass
class History:
    refs: dict[str | None, str] = field(default_factory=lambda: {None: BASE})
    books: dict[str, EdgeBook] = field(default_factory=dict)
    exists: bool = False

    def resolve(self, ref: str | None) -> str | None:
        return self.refs.get(ref)

    def adopted_at(self, ref: str) -> bool:
        return ref in self.books

    def edges_at(self, ref: str) -> EdgeBook | None:
        return self.books.get(ref)

    def has_package(self, ref: str, package: str) -> bool:
        return self.exists

    def policy_at(
        self, ref: str, config_path: Path | None, *, strict: bool
    ) -> LayerConfig | None:
        return None

    def shared_at(self, ref: str, modules: Iterable[str], package: str) -> list[str]:
        return list(modules)

    def head(self) -> str | None:
        return "abc1234"


@dataclass
class Store:
    held: EdgeBook | None = None
    saves: list[EdgeBook] = field(default_factory=list)
    restored: list[str | None] = field(default_factory=list)

    @property
    def path(self) -> str:
        return "layers.json"

    def exists(self) -> bool:
        return self.held is not None

    def book(self) -> EdgeBook:
        return self.held or EdgeBook()

    def save(self, book: EdgeBook) -> None:
        self.saves.append(book)
        self.held = book

    def snapshot(self) -> str | None:
        return "before"

    def restore(self, text: str | None) -> None:
        self.restored.append(text)


@dataclass
class Audit:
    records: list[EdgeRecord] = field(default_factory=list)
    broken: bool = False

    def append(self, record: EdgeRecord) -> None:
        if self.broken:
            raise OSError("disk full")
        self.records.append(record)


@dataclass
class Tree:
    present: set[str] = field(default_factory=set)

    def has_package(self, name: str) -> bool:
        return name in self.present


def ports(
    history: History, store: Store, audit: Audit | None = None, tree: Tree | None = None
) -> EdgePorts:
    return EdgePorts(history, store, audit or Audit(), tree or Tree())


def check(history: History, store: Store, scan: Scan, **flags: bool) -> list[str]:
    run = EdgeCheck(ports(history, store)).run
    args = {"require_base": False, "tripwire": False, "allow_config_change": False}
    verdict = run(scan, base_ref=None, **{**args, **flags})
    return [f.kind for f in verdict.failures]


class TestBook:
    def test_scoped_keeps_the_packages_rows(self) -> None:
        book = EdgeBook(frozenset({KERNEL, OTHER}))
        assert book.scoped("app") == {KERNEL}
        assert book.foreign_roots("app") == {"other"}
        assert book.rooted_in({"other"}) == {OTHER}

    def test_replaced_drops_then_adds(self) -> None:
        book = EdgeBook(frozenset({KERNEL, OTHER}))
        assert book.replaced(frozenset({KERNEL}), frozenset({SERVICE})).edges == {
            OTHER,
            SERVICE,
        }


class TestCheck:
    def test_new_violation_fails(self) -> None:
        history, store = History(books={BASE: EdgeBook()}), Store(EdgeBook())
        assert check(history, store, Scan((KERNEL,))) == ["new-violations"]

    def test_stale_entry_fails(self) -> None:
        book = EdgeBook(frozenset({KERNEL}))
        history, store = History(books={BASE: book}), Store(book)
        assert check(history, store, Scan()) == ["stale-entries"]

    def test_baseline_grown_past_the_base_fails(self) -> None:
        history = History(books={BASE: EdgeBook()}, exists=True)
        store = Store(EdgeBook(frozenset({KERNEL})))
        assert check(history, store, Scan((KERNEL,))) == ["baseline-grown"]

    def test_unchanged_passes(self) -> None:
        book = EdgeBook(frozenset({KERNEL}))
        history, store = History(books={BASE: book}), Store(book)
        assert check(history, store, Scan((KERNEL,))) == []

    def test_unassigned_module_fails(self) -> None:
        history, store = History(books={BASE: EdgeBook()}), Store(EdgeBook())
        scan = Scan(problems=("unassigned module: app.stray",))
        assert check(history, store, scan) == ["not-covered"]

    def test_tree_without_a_baseline_fails_when_the_base_has_one(self) -> None:
        history = History(books={BASE: EdgeBook()})
        assert check(history, Store(None), Scan()) == ["tree-no-baseline"]

    def test_no_base_bootstraps_without_a_baseline(self) -> None:
        assert check(History(refs={}), Store(None), Scan()) == []

    def test_no_base_fails_with_a_baseline(self) -> None:
        assert check(History(refs={}), Store(EdgeBook()), Scan()) == ["base-stale"]

    def test_no_base_fails_when_required(self) -> None:
        kinds = check(History(refs={}), Store(None), Scan(), require_base=True)
        assert kinds == ["base-unresolvable"]


class TestUpdate:
    def _run(
        self, store: Store, scan: Scan, audit: Audit, tree: Tree | None = None
    ) -> EdgeVerdict:
        update = EdgeUpdate(ports(History(), store, audit, tree))
        return update.run(scan, source="PR-1", config_change=False)

    def test_first_update_adopts_every_violation(self) -> None:
        store, audit = Store(), Audit()
        result = self._run(store, Scan((KERNEL,)), audit)
        assert result.passed
        assert store.saves == [EdgeBook(frozenset({KERNEL}))]
        (record,) = audit.records
        assert (record.verdict, record.added, record.source) == (
            "adopt",
            frozenset({KERNEL}),
            "PR-1",
        )

    def test_a_new_violation_is_refused_and_nothing_is_written(self) -> None:
        store, audit = Store(EdgeBook(frozenset({KERNEL}))), Audit()
        result = self._run(store, Scan((KERNEL, SERVICE)), audit)
        assert result.failures == (Failure("refuse-new", (str(SERVICE),)),)
        assert (store.saves, audit.records) == ([], [])

    def test_a_fix_shrinks_the_baseline(self) -> None:
        store, audit = Store(EdgeBook(frozenset({KERNEL}))), Audit()
        assert self._run(store, Scan(), audit).passed
        assert store.saves == [EdgeBook()]
        assert audit.records[0].removed == {KERNEL}

    def test_rows_of_a_deleted_package_are_retired(self) -> None:
        store = Store(EdgeBook(frozenset({KERNEL, OTHER})))
        audit = Audit()
        self._run(store, Scan((KERNEL,)), audit, Tree({"app"}))
        assert store.saves == [EdgeBook(frozenset({KERNEL}))]
        assert audit.records[0].retired == {OTHER}

    def test_rows_of_a_live_package_stay(self) -> None:
        store = Store(EdgeBook(frozenset({KERNEL, OTHER})))
        self._run(store, Scan((KERNEL,)), Audit(), Tree({"app", "other"}))
        assert store.saves == [EdgeBook(frozenset({KERNEL, OTHER}))]

    def test_a_failed_audit_puts_the_baseline_back(self) -> None:
        store, audit = Store(), Audit(broken=True)
        with pytest.raises(OSError, match="disk full"):
            self._run(store, Scan((KERNEL,)), audit)
        assert store.restored == ["before"]
