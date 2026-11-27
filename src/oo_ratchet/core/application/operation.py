"""The collaborators every operation holds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from .policy import GatePolicy
from .ports import AuditSink, BaselineStore, History, SourceReader


@dataclass(frozen=True, slots=True)
class Ports:
    """The four ports a gate's adapters fill."""

    history: History
    store: BaselineStore
    audit: AuditSink
    source: SourceReader


class Operation:
    """A gate operation: the gate's policy and the ports it works through."""

    _policy: GatePolicy
    _ports: Ports
    _history: History
    _store: BaselineStore
    _audit: AuditSink
    _source: SourceReader

    def __new__(cls, policy: GatePolicy, ports: Ports) -> Self:
        self = super().__new__(cls)
        self._policy = policy
        self._ports = ports
        self._history = ports.history
        self._store = ports.store
        self._audit = ports.audit
        self._source = ports.source
        return self
