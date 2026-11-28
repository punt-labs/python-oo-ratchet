"""The OO gate wired to a repository: its operations and views, rendered."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Self

from oo_ratchet.core.application.check import Check
from oo_ratchet.core.application.oowaive import OoRebaselineFiles
from oo_ratchet.core.application.operation import Ports
from oo_ratchet.core.application.policy import GatePolicy
from oo_ratchet.core.application.reconcile import Reconcile
from oo_ratchet.core.application.update import Update
from oo_ratchet.core.application.waive import Rebaseline, Relax
from oo_ratchet.source_set import Source, SourceSelection

from .gatecli import GateCli
from .gitrepo import GitRepo
from .jsonstore import AuditFile
from .oocli import OoCli
from .oorequest import Requested
from .oostore import OoBaselineStore
from .ootree import OoTree

if TYPE_CHECKING:
    from oo_ratchet.oo.scorer import Scorer

BASELINE = ".oo-baseline.json"
AUDIT = ".oo-audit.jsonl"

Report = tuple[list[str], int]


class OoGate:
    """Run one OO command line: an operation or a view, in the current repository.

    ``run`` returns the report lines and the exit code. A corrupt baseline or
    audit log, or a failed git call, is a failing report, never a traceback.
    """

    _req: Requested
    _git: GitRepo
    _root: Path
    _views: OoCli
    _policy: GatePolicy
    _score: Callable[[Source, Path], Scorer]

    def __new__(
        cls,
        request: Requested,
        score: Callable[[Source, Path], Scorer],
        policy: GatePolicy,
    ) -> Self:
        self = super().__new__(cls)
        self._req = request
        self._score = score
        self._git = GitRepo(Path.cwd(), BASELINE, AUDIT)
        self._root = self._git.root or Path.cwd()
        self._views = OoCli(self._root / BASELINE)
        self._policy = policy
        return self

    def run(self) -> Report:
        """Execute the requested operation and return its report."""
        guard = self._rebaseline_files_guard()
        if guard is not None:
            return guard
        req = self._req
        if not SourceSelection.path(req.src).exists():
            return [f"Not found: {req.src}"], 1
        scorer = self._score(req.src, self._root)
        return self._dispatch(scorer)

    def _rebaseline_files_guard(self) -> Report | None:
        """Refuse a malformed ``--rebaseline-files`` before the target is scored."""
        paths = self._req.rebaseline_files
        if paths is None:
            return None
        if not paths:
            return ["FAIL: --rebaseline-files requires at least one path"], 1
        if not self._req.reason.strip():
            return ["FAIL: --rebaseline-files requires --reason <text>"], 1
        return None

    def _dispatch(self, scorer: Scorer) -> Report:
        req = self._req
        if not (req.log or req.json) and self._unscorable(scorer):
            return [f"FAIL: cannot score {req.src}"], 1
        ports = Ports(
            self._git,
            OoBaselineStore(self._root / BASELINE),
            AuditFile(self._root / AUDIT),
            OoTree(self._root, scorer, self._policy.names),
        )
        ports.store.rows()  # a corrupt baseline fails every command, views included
        action = self._action(ports, scorer)
        return action if action is not None else self._view(scorer)

    def _unscorable(self, scorer: Scorer) -> bool:
        """Return whether a single-file target produced only an error row."""
        return SourceSelection.path(self._req.src).is_file() and bool(
            scorer.parse_errors
        )

    def _action(self, ports: Ports, scorer: Scorer) -> Report | None:
        req = self._req
        if req.check:
            return self._check(ports)
        if req.rebaseline:
            return self._write(self._rebaseline, ports)
        if req.reconcile:
            return self._write(self._reconcile, ports)
        if req.relax is not None:
            return self._write(self._relax, ports)
        if req.rebaseline_files is not None:
            return self._write(self._bless, ports)
        if req.update:
            return self._write(self._update, ports)
        if req.log:
            return self._log(ports)
        if req.audit_completeness:
            return self._completeness(ports, scorer)
        return None

    def _check(self, ports: Ports) -> Report:
        req = self._req
        verdict = Check(self._policy, ports).run(
            base_ref=req.base_ref,
            require_base=req.require_base,
            allow_no_improvement=req.allow_no_improvement,
            tripwire=req.tripwire,
        )
        return self._views.check(verdict), self._views.exit_code(verdict)

    def _write(self, operation: _Write, ports: Ports) -> Report:
        """Run a baseline write unless CI forbids it."""
        blocked = GateCli.write_blocked(allow_ci_write=self._req.allow_ci_write)
        if blocked is not None:
            return [f"FAIL: {OoCli.COMMON['ci-write']}"], 1
        return operation(ports)

    def _update(self, ports: Ports) -> Report:
        req = self._req
        verdict = Update(self._policy, ports).run(
            base_ref=req.base_ref, require_base=req.require_base, source=req.source
        )
        return self._views.update(verdict), self._views.exit_code(verdict)

    def _reconcile(self, ports: Ports) -> Report:
        verdict = Reconcile(self._policy, ports).run(source=self._req.source)
        return self._views.update(verdict), self._views.exit_code(verdict)

    def _relax(self, ports: Ports) -> Report:
        req = self._req
        file = req.relax or ""
        verdict = Relax(self._policy, ports).run(
            file, justify=req.justify, source=req.source
        )
        return self._views.relax(verdict, file, req.justify), self._views.exit_code(
            verdict
        )

    def _bless(self, ports: Ports) -> Report:
        req = self._req
        verdict = OoRebaselineFiles(self._policy, ports).run(
            list(req.rebaseline_files or ()), reason=req.reason, source=req.source
        )
        return self._views.bless(verdict, req.reason), self._views.exit_code(verdict)

    def _rebaseline(self, ports: Ports) -> Report:
        verdict = Rebaseline(self._policy, ports).run(source=self._req.source)
        return self._views.rebaseline(verdict), self._views.exit_code(verdict)

    def _log(self, ports: Ports) -> Report:
        if not (self._root / AUDIT).exists():
            return ["No audit log found"], 0
        return self._views.log(ports.audit.records()), 0

    @staticmethod
    def _completeness(ports: Ports, scorer: Scorer) -> Report:
        """Fail if any scored file is absent from the in-tree baseline."""
        missing = sorted(scorer.files - set(ports.store.rows()))
        if missing:
            return [
                "FAIL: files missing from baseline:",
                *(f"  {p}" for p in missing),
            ], 1
        return [f"PASS: baseline complete for {len(scorer.files)} scored files"], 0

    def _view(self, scorer: Scorer) -> Report:
        code = 1 if scorer.fail_count > 0 or scorer.parse_errors else 0
        if self._req.json:
            return [scorer.to_json()], code
        lines = list(scorer.render_table())
        if self._req.threshold:
            lines.extend(scorer.render_per_file())
        return lines, code


type _Write = Callable[[Ports], Report]
