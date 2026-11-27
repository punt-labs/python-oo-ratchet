"""A per-file metric gate wired to a repository: its operations, rendered."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Self

from oo_ratchet.core.application.blessbase import BlessBase
from oo_ratchet.core.application.check import Check
from oo_ratchet.core.application.operation import Ports
from oo_ratchet.core.application.policy import GatePolicy
from oo_ratchet.core.application.update import Update
from oo_ratchet.core.application.waive import Rebaseline, RebaselineFiles, Relax
from oo_ratchet.core.domain.scores import Measurement
from oo_ratchet.core.domain.verdicts import Verdict

from .auditview import AuditView
from .couplingformats import CouplingAuditFormat
from .couplingview import CouplingView
from .gatecli import GateCli
from .gitrepo import GitRepo
from .jsonstore import AuditFile, JsonBaselineStore
from .scoredtree import ScoredTree


@dataclass(frozen=True, slots=True)
class MetricFiles:
    """The names of a gate's two state files, at the repository root."""

    baseline: str
    audit: str


Report = tuple[list[str], int]


class MetricGate:
    """Run the per-file operations of the coupling gate in a repository.

    Each operation returns the report lines and the exit code. ``prepare``
    binds the tree the CLI scored; no operation runs before it.
    """

    @dataclass(frozen=True, slots=True)
    class BlessRequest:
        """One scoped bless: the files, why, and the base they are judged on."""

        paths: list[str]
        reason: str
        allow_ci_write: bool
        source: str | None
        base_ref: str | None
        require_base: bool

    _files: MetricFiles
    _git: GitRepo
    _root: Path
    _run: tuple[GatePolicy, Ports] | None
    _view: CouplingView

    def __new__(cls, files: MetricFiles) -> Self:
        self = super().__new__(cls)
        self._files = files
        self._git = GitRepo(Path.cwd(), files.baseline, files.audit)
        self._root = self._git.root or Path.cwd()
        self._run = None
        self._view = CouplingView(self._root / files.baseline)
        return self

    @property
    def root(self) -> Path:
        """Return the repository root, the working directory outside a repo."""
        return self._root

    def prepare(self, policy: GatePolicy, measurement: Measurement) -> None:
        """Bind the policy and the scored tree, and read the recorded rows.

        A corrupt in-tree baseline fails here, whichever operation follows.
        """
        files, root = self._files, self._root
        store = JsonBaselineStore(root / files.baseline)
        store.rows()
        audit = AuditFile(root / files.audit, CouplingAuditFormat)
        tree = ScoredTree(root, measurement)
        self._run = (policy, Ports(self._git, store, audit, tree))

    def check(
        self, *, base_ref: str | None, require_base: bool, tripwire: bool
    ) -> Report:
        """Compare the touched files with the baseline at the base."""
        verdict = Check(*self._bound()).run(
            base_ref=base_ref, require_base=require_base, tripwire=tripwire
        )
        return self._view.check(verdict), self._code(verdict)

    def update(
        self,
        *,
        base_ref: str | None,
        require_base: bool,
        allow_ci_write: bool,
        source: str | None,
    ) -> Report:
        """Record the touched files' scores, never loosening a row."""
        verdict = GateCli.write_blocked(allow_ci_write=allow_ci_write)
        if verdict is None:
            verdict = Update(*self._bound()).run(
                base_ref=base_ref, require_base=require_base, source=source
            )
        return self._view.update(verdict), self._code(verdict)

    def relax(
        self, file: str, *, justify: str, allow_ci_write: bool, source: str | None
    ) -> Report:
        """Record ``file``'s scores even where looser, with a justification."""
        verdict = GateCli.write_blocked(allow_ci_write=allow_ci_write)
        if verdict is None:
            verdict = Relax(*self._bound()).run(file, justify=justify, source=source)
        return self._view.relax(verdict, file, justify), self._code(verdict)

    def rebaseline(
        self, *, reason: str, allow_ci_write: bool, source: str | None
    ) -> Report:
        """Reset the baseline to the current scores."""
        verdict = GateCli.write_blocked(allow_ci_write=allow_ci_write)
        if verdict is None:
            verdict = Rebaseline(*self._bound()).run(
                source=source, reason=reason, detail=True
            )
        return self._view.rebaseline(verdict), self._code(verdict)

    def bless(self, request: MetricGate.BlessRequest) -> Report:
        """Record the named files' scores where they clear their caps."""
        verdict = self._blessed(request)
        return self._view.bless(verdict, request.reason), self._code(verdict)

    def log(self) -> Report:
        """Return the audit history."""
        view = AuditView(self._root / self._files.audit, "coupling")
        return view.lines(), 0

    def _blessed(self, request: MetricGate.BlessRequest) -> Verdict:
        blocked = GateCli.write_blocked(allow_ci_write=request.allow_ci_write)
        if blocked is not None:
            return blocked
        if not request.reason.strip():
            return Verdict.refused("blank-reason")
        policy, ports = self._bound()
        loaded = BlessBase.load(
            ports.history, request.base_ref, require_base=request.require_base
        )
        if isinstance(loaded, Verdict):
            return loaded
        bless = RebaselineFiles(policy, ports)
        return bless.run(
            request.paths, reason=request.reason, source=request.source, base=loaded
        )

    def _bound(self) -> tuple[GatePolicy, Ports]:
        if self._run is None:
            msg = "prepare() must bind the scored tree first"
            raise RuntimeError(msg)
        return self._run

    @staticmethod
    def _code(verdict: Verdict) -> int:
        return GateCli.exit_code(verdict)
