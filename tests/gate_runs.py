"""Drive the OO gate on a repository without going through ``argv``.

``Request`` is a parsed OO command line with every flag off. ``Ratchet`` and
``Writer`` run one operation of ``OoGate`` in a given repository and return its
report as an ``Outcome``, the shape the OO tests assert on.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Self

from oo_ratchet.core.adapters.oogate import OoGate
from oo_ratchet.oo.cli import POLICY
from oo_ratchet.oo.scorer import Scorer
from oo_ratchet.source_set import Source


@dataclass(frozen=True)
class Outcome:
    """An exit code and the report lines."""

    exit_code: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class Request:
    """A parsed OO command line."""

    src: Source
    check: bool = False
    update: bool = False
    reconcile: bool = False
    rebaseline: bool = False
    log: bool = False
    json: bool = False
    threshold: bool = False
    audit_completeness: bool = False
    relax: str | None = None
    rebaseline_files: tuple[str, ...] | None = None
    justify: str = ""
    reason: str = ""
    base_ref: str | None = None
    require_base: bool = False
    allow_no_improvement: bool = False
    tripwire: bool = False
    allow_ci_write: bool = False
    source: str | None = None


class Scored(Scorer):
    """A ``Scorer`` that remembers what it scored."""

    _target: Source

    def __new__(cls, target: Source, root: Path) -> Self:
        self = super().__new__(cls, target, root)
        self._target = target
        return self

    @property
    def target(self) -> Source:
        """Return the scored target."""
        return self._target


def run(root: Path, request: Request) -> Outcome:
    """Run ``request`` in ``root`` and return the report."""
    before = Path.cwd()
    os.chdir(root)
    try:
        lines, code = OoGate(request, Scorer, POLICY).run()
    finally:
        os.chdir(before)
    return Outcome(code, tuple(lines))


class Ratchet:
    """The checks and views of the OO gate in one repository."""

    _root: Path

    def __new__(cls, root: Path) -> Self:
        self = super().__new__(cls)
        self._root = root
        return self

    def check(
        self,
        scorer: Scored,
        *,
        base_ref: str | None,
        require_base: bool,
        allow_no_improvement: bool = False,
        tripwire: bool = False,
    ) -> Outcome:
        """Run ``--check``."""
        request = Request(
            scorer.target,
            check=True,
            base_ref=base_ref,
            require_base=require_base,
            allow_no_improvement=allow_no_improvement,
            tripwire=tripwire,
        )
        return run(self._root, request)

    def show_log(self, scorer: Scored) -> Outcome:
        """Run ``--log``."""
        return run(self._root, Request(scorer.target, log=True))

    def audit_completeness(self, scorer: Scored) -> Outcome:
        """Run ``--audit-completeness``."""
        return run(self._root, Request(scorer.target, audit_completeness=True))


class Writer:
    """The baseline writes of the OO gate in one repository."""

    _root: Path

    def __new__(cls, root: Path) -> Self:
        self = super().__new__(cls)
        self._root = root
        return self

    def update(
        self,
        scorer: Scored,
        *,
        base_ref: str | None,
        require_base: bool,
        allow_ci_write: bool,
        source: str | None,
    ) -> Outcome:
        """Run ``--update``."""
        request = Request(
            scorer.target,
            update=True,
            base_ref=base_ref,
            require_base=require_base,
            allow_ci_write=allow_ci_write,
            source=source,
        )
        return run(self._root, request)

    def reconcile(
        self, scorer: Scored, *, allow_ci_write: bool, source: str | None
    ) -> Outcome:
        """Run ``--reconcile``."""
        request = Request(
            scorer.target,
            reconcile=True,
            allow_ci_write=allow_ci_write,
            source=source,
        )
        return run(self._root, request)

    def relax(
        self,
        scorer: Scored,
        file: str,
        *,
        justify: str,
        allow_ci_write: bool,
        source: str | None,
    ) -> Outcome:
        """Run ``--relax``."""
        request = Request(
            scorer.target,
            relax=file,
            justify=justify,
            allow_ci_write=allow_ci_write,
            source=source,
        )
        return run(self._root, request)

    def rebaseline_files(
        self,
        scorer: Scored,
        paths: list[str],
        *,
        reason: str,
        allow_ci_write: bool,
        source: str | None,
    ) -> Outcome:
        """Run ``--rebaseline-files``."""
        request = Request(
            scorer.target,
            rebaseline_files=tuple(paths),
            reason=reason,
            allow_ci_write=allow_ci_write,
            source=source,
        )
        return run(self._root, request)

    def rebaseline(
        self, scorer: Scored, *, allow_ci_write: bool, source: str | None
    ) -> Outcome:
        """Run ``--rebaseline``."""
        request = replace(
            Request(scorer.target),
            rebaseline=True,
            allow_ci_write=allow_ci_write,
            source=source,
        )
        return run(self._root, request)
