"""What the OO gate needs to know about one command line."""

from __future__ import annotations

from typing import Protocol

from oo_ratchet.source_set import Source


class Requested(Protocol):
    """A parsed OO command line: the target, the action and its modifiers.

    Read-only, so a frozen options object satisfies it.
    """

    @property
    def src(self) -> Source: ...

    @property
    def check(self) -> bool: ...

    @property
    def update(self) -> bool: ...

    @property
    def reconcile(self) -> bool: ...

    @property
    def rebaseline(self) -> bool: ...

    @property
    def log(self) -> bool: ...

    @property
    def json(self) -> bool: ...

    @property
    def threshold(self) -> bool: ...

    @property
    def audit_completeness(self) -> bool: ...

    @property
    def relax(self) -> str | None: ...

    @property
    def rebaseline_files(self) -> tuple[str, ...] | None: ...

    @property
    def justify(self) -> str: ...

    @property
    def reason(self) -> str: ...

    @property
    def base_ref(self) -> str | None: ...

    @property
    def require_base(self) -> bool: ...

    @property
    def allow_no_improvement(self) -> bool: ...

    @property
    def tripwire(self) -> bool: ...

    @property
    def allow_ci_write(self) -> bool: ...

    @property
    def source(self) -> str | None: ...
