"""A total-count gate wired to a repository: its operations, rendered."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from oo_ratchet.core.application.tallyops import (
    TallyCheck,
    TallyRebaseline,
    TallyRelax,
    TallyUpdate,
)
from oo_ratchet.core.application.tallyports import TallyPorts
from oo_ratchet.core.domain.tallies import Tally
from oo_ratchet.core.domain.tallyverdicts import TallyVerdict
from oo_ratchet.source_set import Source

from .gatecli import GateCli
from .gitrepo import GitRepo
from .tallycli import TallyCli
from .tallyfiles import JsonLedger, JsonTallyStore, TallyAuditFile
from .tallyrepo import TallyRepo


@dataclass(frozen=True, slots=True)
class GateFiles:
    """The names of a gate's three state files, at the repository root."""

    baseline: str
    audit: str
    ledger: str


Report = tuple[list[str], int]


class TallyGate:
    """Run a total-count gate's operations in a repository.

    Each operation returns the report lines and the exit code. ``scan`` is the
    gate's scanner: it counts a source selection, in the work tree or at a
    commit.
    """

    _files: GateFiles
    _target: Source
    _scan: Callable[[Source, Path], Tally]
    _git: GitRepo
    _root: Path
    _ports: TallyPorts | None
    _views: TallyCli

    def __new__(
        cls, files: GateFiles, target: Source, scan: Callable[[Source, Path], Tally]
    ) -> Self:
        self = super().__new__(cls)
        self._files = files
        self._target = target
        self._scan = scan
        self._git = GitRepo(Path.cwd(), files.baseline, files.audit)
        self._root = self._git.root or Path.cwd()
        self._ports = None
        self._views = TallyCli(files.ledger)
        return self

    @property
    def root(self) -> Path:
        """Return the repository root, the working directory outside a repo."""
        return self._root

    def prepare(self) -> None:
        """Read the recorded state; a corrupt baseline or ledger fails here."""
        self._open()

    def check(
        self, tally: Tally, *, base_ref: str | None, require_base: bool, tripwire: bool
    ) -> Report:
        """Compare ``tally`` with the source at the base."""
        check = TallyCheck(self._open())
        return self._report(
            check.run(
                tally, base_ref=base_ref, require_base=require_base, tripwire=tripwire
            )
        )

    def update(self, tally: Tally, *, allow_ci_write: bool) -> Report:
        """Record ``tally`` as the baseline, never loosening it."""
        blocked = self._blocked(allow_ci_write=allow_ci_write)
        if blocked is not None:
            return blocked
        return self._report(TallyUpdate(self._open()).run(tally))

    def rebaseline(
        self,
        tally: Tally,
        *,
        reason: str,
        source: str | None,
        allow_ci_write: bool,
    ) -> Report:
        """Reset the baseline to ``tally``, with an audited reason."""
        blocked = self._blocked(allow_ci_write=allow_ci_write)
        if blocked is not None:
            return blocked
        rebaseline = TallyRebaseline(self._open())
        return self._report(rebaseline.run(tally, reason=reason, source=source))

    def relax(
        self,
        tally: Tally,
        *,
        base_ref: str | None,
        file: str,
        justify: str,
        allow_ci_write: bool,
    ) -> Report:
        """Record a justified ceiling for ``file`` at its current count."""
        blocked = self._blocked(allow_ci_write=allow_ci_write)
        if blocked is not None:
            return blocked
        relax = TallyRelax(self._open())
        verdict = relax.run(
            tally,
            target=str(self._target),
            base_ref=base_ref,
            file=file,
            justify=justify,
        )
        return self._report(verdict)

    def _open(self) -> TallyPorts:
        if self._ports is None:
            files, root = self._files, self._root
            history = TallyRepo(self._git, self._target, root, self._scan, files.ledger)
            self._ports = TallyPorts(
                history,
                JsonTallyStore(root / files.baseline),
                JsonLedger(root / files.ledger),
                TallyAuditFile(root / files.audit),
            )
        return self._ports

    def _blocked(self, *, allow_ci_write: bool) -> Report | None:
        refusal = GateCli.write_blocked(allow_ci_write=allow_ci_write)
        return None if refusal is None else self._report(TallyVerdict(refusal))

    def _report(self, result: TallyVerdict) -> Report:
        return self._views.text(result), self._views.exit_code(result)
