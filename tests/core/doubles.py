"""In-memory ports for the operation tests: no git, no filesystem."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from oo_ratchet.core.application.operation import Ports
from oo_ratchet.core.application.policy import GatePolicy
from oo_ratchet.core.domain.changes import Diff
from oo_ratchet.core.domain.records import AuditRecord
from oo_ratchet.core.domain.scores import Measurement, Rows, Score
from oo_ratchet.oo.thresholds import OO_METRICS

BASE = "base0"
TIP = "tip0"


def oo_policy() -> GatePolicy:
    """The OO gate's policy, built from the existing threshold table."""
    return GatePolicy(OO_METRICS.items)


def coupling_policy() -> GatePolicy:
    """A regression-only policy over two metrics, like the coupling gate."""
    table = {"efferent_coupling": ("<=", 10), "max_lcom": ("<=", 0.8)}
    return GatePolicy.from_table(
        table, must_improve=False, absolute_targets=False, lock_rows=False
    )


@dataclass
class FakeHistory:
    """The past: refs, the baselines and audit logs committed at them."""

    refs: dict[str | None, str] = field(default_factory=lambda: {None: BASE})
    baselines: dict[str, Rows | None] = field(default_factory=dict)
    audits: dict[str, tuple[AuditRecord, ...] | None] = field(default_factory=dict)
    diff: Diff = field(default_factory=Diff)
    short: str | None = "abc1234"

    def resolve(self, ref: str | None) -> str | None:
        """Return the base a ref names."""
        return self.refs.get(ref)

    def baseline_at(self, ref: str) -> Rows | None:
        """Return the baseline at ``ref``."""
        return copy.deepcopy(self.baselines.get(ref))

    def adopted_at(self, ref: str) -> bool:
        """Return whether a baseline exists at ``ref``."""
        return self.baselines.get(ref) is not None

    def audit_at(self, ref: str) -> tuple[AuditRecord, ...] | None:
        """Return the audit log at ``ref``."""
        return self.audits.get(ref)

    def changes_since(self, base: str) -> Diff:
        """Return the configured diff."""
        return self.diff

    def head(self) -> str | None:
        """Return the configured HEAD."""
        return self.short


@dataclass
class MemoryStore:
    """The in-tree baseline held in a dict."""

    data: Rows | None = None

    def exists(self) -> bool:
        """Return whether a baseline was saved or given."""
        return self.data is not None

    def rows(self) -> Rows:
        """Return a copy of the rows."""
        return copy.deepcopy(self.data or {})

    def save(self, rows: Rows) -> None:
        """Replace the rows."""
        self.data = copy.deepcopy(dict(sorted(rows.items())))


@dataclass
class MemoryAudit:
    """The audit trail held in a list."""

    log: list[AuditRecord] = field(default_factory=list)

    def append(self, record: AuditRecord) -> None:
        """Add a record."""
        self.log.append(record)

    def records(self) -> tuple[AuditRecord, ...]:
        """Return the records."""
        return tuple(self.log)


@dataclass
class FakeSource:
    """A work tree: the scores a scan finds and the files on disk."""

    scores: dict[str, dict[str, float]] = field(default_factory=dict)
    broken: frozenset[str] = frozenset()
    disk: set[str] | None = None

    def measure(self) -> Measurement:
        """Return the configured scan."""
        return Measurement(
            tuple(Score(p, m) for p, m in self.scores.items()), self.broken
        )

    def exists(self, path: str) -> bool:
        """Return whether ``path`` is on disk."""
        on_disk = set(self.scores) | self.broken if self.disk is None else self.disk
        return path in on_disk

    def key(self, requested: str) -> str:
        """Return the key for a spelling of a path."""
        return requested.removeprefix("./")


@dataclass
class World:
    """One gate's ports, wired together for a test."""

    history: FakeHistory = field(default_factory=FakeHistory)
    store: MemoryStore = field(default_factory=MemoryStore)
    audit: MemoryAudit = field(default_factory=MemoryAudit)
    source: FakeSource = field(default_factory=FakeSource)

    def args(self, policy: GatePolicy) -> tuple[GatePolicy, Ports]:
        """Return the constructor arguments every operation takes."""
        return policy, Ports(self.history, self.store, self.audit, self.source)
