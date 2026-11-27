"""The layers gate wired to a repository: its operations, rendered."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from oo_ratchet.core.application.edgeops import EdgeCheck, EdgeUpdate
from oo_ratchet.core.application.edgeports import EdgePorts, Survey
from oo_ratchet.core.domain.edges import EdgeVerdict
from oo_ratchet.core.domain.errors import GitError
from oo_ratchet.source_set import Source, SourceSet

from .edgecli import EdgeCli
from .edgefiles import EdgeAuditFile, JsonEdgeStore
from .edgerepo import EdgeRepo
from .gatecli import GateCli
from .gitrepo import GitRepo
from .treeviews import WorkingTree

Report = tuple[list[str], int]


class EdgeGate:
    """Run the layers gate's check and update in a repository.

    Each operation returns the report lines and the exit code. ``scan`` is the
    scanned package; ``git`` is built by ``repo`` for the package's directory.
    """

    BASELINE = ".oo-layers-baseline.json"
    AUDIT = ".oo-layers-audit.jsonl"

    _src: Source
    _scan: Survey
    _git: GitRepo
    _root: Path
    _views: EdgeCli

    def __new__(cls, src: Source, scan: Survey, git: GitRepo) -> Self:
        self = super().__new__(cls)
        root = git.root
        if root is None:
            raise GitError("not inside a git repository")
        self._src = src
        self._scan = scan
        self._git = git
        self._root = root
        self._views = EdgeCli()
        return self

    @classmethod
    def repo(cls, src: Source) -> GitRepo:
        """Return the git adapter for the repository holding ``src``."""
        start = SourceSet(src).start_dir or Path.cwd()
        return GitRepo(start, cls.BASELINE, cls.AUDIT)

    def check(
        self,
        *,
        base_ref: str | None,
        require_base: bool,
        tripwire: bool,
        allow_config_change: bool,
    ) -> Report:
        """Compare the scan with the baseline and the base."""
        check = EdgeCheck(self._open())
        return self._report(
            check.run(
                self._scan,
                base_ref=base_ref,
                require_base=require_base,
                tripwire=tripwire,
                allow_config_change=allow_config_change,
            )
        )

    def update(
        self, *, allow_ci_write: bool, source: str | None, config_change: bool
    ) -> Report:
        """Write the scan's violations as the baseline, never adding one."""
        ports = self._open(tree=WorkingTree(self._root))
        refusal = GateCli.write_blocked(allow_ci_write=allow_ci_write)
        if refusal is not None:
            return self._report(EdgeVerdict(refusal))
        update = EdgeUpdate(ports)
        return self._report(
            update.run(self._scan, source=source, config_change=config_change)
        )

    def _open(self, tree: WorkingTree | None = None) -> EdgePorts:
        """Build the ports; a corrupt in-tree baseline fails here."""
        root = self._root
        history = EdgeRepo(self._git, root, self._src, self.BASELINE)
        store = JsonEdgeStore(root / self.BASELINE)
        audit = EdgeAuditFile(root / self.AUDIT)
        return EdgePorts(history, store, audit, tree or _NoTree())

    def _report(self, result: EdgeVerdict) -> Report:
        return self._views.text(result), self._views.exit_code(result)


class _NoTree:
    """The checkout of a check, which never asks whether a package exists."""

    def has_package(self, name: str) -> bool:
        """Fail: a check has no working tree to read."""
        raise GitError(f"no working tree was read for package {name!r}")
