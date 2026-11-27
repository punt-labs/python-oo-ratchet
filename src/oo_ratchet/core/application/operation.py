"""The collaborators every operation holds."""

from __future__ import annotations

from typing import Self

from .policy import GatePolicy
from .ports import AuditSink, BaselineStore, History, SourceReader


class Operation:
    """A gate operation: the gate's policy and the four ports it works through."""

    _policy: GatePolicy
    _history: History
    _store: BaselineStore
    _audit: AuditSink
    _source: SourceReader

    def __new__(
        cls,
        policy: GatePolicy,
        history: History,
        store: BaselineStore,
        audit: AuditSink,
        source: SourceReader,
    ) -> Self:
        self = super().__new__(cls)
        self._policy = policy
        self._history = history
        self._store = store
        self._audit = audit
        self._source = source
        return self
