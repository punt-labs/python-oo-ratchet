"""The repository's past as a total-count gate sees it: ``TallyHistory``."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Self

from oo_ratchet.core.domain.errors import GitError
from oo_ratchet.core.domain.ledgers import Ledger
from oo_ratchet.core.domain.tallies import Tally
from oo_ratchet.source_set import Source, SourceSet

from .gitrepo import GitRepo
from .tallyformats import LedgerFormat


class TallyRepo:
    """Count the source as it stood at a commit, with the gate's own scanner.

    The base side is a rescan of the commit's real source, materialized with
    ``git archive`` and scanned by the same function as the work tree, so the
    two counts cannot disagree about what counts. ``scan`` is the gate's
    scanner: it knows what a suppression is.
    """

    _git: GitRepo
    _target: Source
    _root: Path
    _scan: Callable[[Source, Path], Tally]
    _ledger_file: str

    def __new__(
        cls,
        git: GitRepo,
        target: Source,
        root: Path,
        scan: Callable[[Source, Path], Tally],
        ledger_file: str,
    ) -> Self:
        self = super().__new__(cls)
        self._git = git
        self._target = target
        self._root = root
        self._scan = scan
        self._ledger_file = ledger_file
        return self

    def resolve(self, ref: str | None) -> str | None:
        """Return the comparison base: ``ref``, else the merge base of main."""
        return self._git.resolve(ref)

    def head(self) -> str | None:
        """Return the abbreviated HEAD commit."""
        return self._git.head()

    def adopted_at(self, ref: str) -> bool:
        """Return whether the scanned source tree exists at ``ref``."""
        return self._git.exists_at(ref, self._relpath(self._target))

    def ledger_at(self, ref: str) -> Ledger | None:
        """Return the ledger committed at ``ref``, ``None`` if absent.

        A malformed committed ledger fails closed, naming the in-tree path.
        """
        text = self._git.show(ref, self._ledger_file)
        if text is None:
            return None
        return LedgerFormat.decode(text, str(self._root / self._ledger_file))

    def tally_at(self, ref: str) -> Tally | None:
        """Return a fresh count of the target as it existed at ``ref``.

        ``None`` when the target did not exist at ``ref``.
        """
        return SourceSet(self._target).rescan(
            ref, self._git, self._single, self._scan, Tally.rebased
        )

    def _single(self, ref: str, target: Path) -> Tally | None:
        target_rel = self._relpath(target)
        if not self._git.exists_at(ref, target_rel):
            return None
        project_rel = self._relpath(self._root)
        pyproject_rel = (
            f"{project_rel}/pyproject.toml" if project_rel else "pyproject.toml"
        )
        paths = [target_rel or "."]  # git rejects "" as a pathspec
        if self._git.exists_at(ref, pyproject_rel):
            paths.append(pyproject_rel)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            self._git.archive_paths(ref, paths, tmp_root)
            project_root = tmp_root / project_rel if project_rel else tmp_root
            scan_target = tmp_root / target_rel
            scanned = self._scan(scan_target, project_root)
            # Rewire by_file keys from the temporary root onto ``target``
            # itself: both sides must key a file the same way.
            old, new = str(scan_target), str(target)
            if scan_target.is_dir():
                # Rebase whole segments; a "." target keys files as "pkg/a.py".
                old += "/"
                new = "" if new == "." else new.rstrip("/") + "/"
            return scanned.rebased(old, new)

    def _relpath(self, path: Source) -> str:
        """Return ``path`` as a POSIX path relative to the repository root.

        Git pathspecs are root-relative. The root itself is ``""``, not ``"."``,
        which git rejects.
        """
        git_root = self._git.root
        if git_root is None:
            raise GitError("not inside a git repository")
        resolved = SourceSet.path(path).resolve()
        try:
            rel = resolved.relative_to(git_root.resolve())
        except ValueError as exc:
            raise GitError(
                f"{resolved} is outside the git repository at {git_root}"
            ) from exc
        rel_str = rel.as_posix()
        return "" if rel_str == "." else rel_str
