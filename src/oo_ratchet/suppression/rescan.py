"""Rescan a target's real source tree as it existed at a historical git ref."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Self

from oo_ratchet.source_set import Source, SourceSet

from .gitio import GitError, GitRepo
from .report import SuppressionReport
from .scanner import Scanner


class BaseRescanner:
    """Materialize a target at a git ref and scan it through the live pipeline.

    Rescanning the base commit's real source tree, rather than trusting a
    committed baseline blob, guarantees the current and base counts can never
    disagree about what counts as a suppression -- there is no second,
    independently-maintained source of truth to drift out of sync.
    """

    _git: GitRepo
    _pyproject_dir: Path

    def __new__(cls, git: GitRepo, pyproject_dir: Path) -> Self:
        self = super().__new__(cls)
        self._git = git
        self._pyproject_dir = pyproject_dir
        return self

    def rescan(self, ref: str, target: Source) -> SuppressionReport | None:
        """Return a fresh report of ``target`` as it existed at ``ref``.

        Materializes the real historical ``target`` (and ``pyproject.toml``,
        when present) into a temp directory and runs it through the same
        ``Scanner`` used for the current tree. Returns ``None`` when
        ``target`` did not exist at ``ref`` (the ref predates the scanned
        source tree).
        """
        return SourceSet(target).rescan(
            ref, self._git, self._single, self._scan, SuppressionReport.rebased
        )

    @staticmethod
    def _scan(target: Source, project: Path) -> SuppressionReport:
        return Scanner(target, project).report

    def _single(self, ref: str, target: Path) -> SuppressionReport | None:
        target_rel = self.relpath(target)
        if not self._git.path_exists_at_ref(ref, target_rel):
            return None
        project_rel = self.relpath(self._pyproject_dir)
        pyproject_rel = (
            f"{project_rel}/pyproject.toml" if project_rel else "pyproject.toml"
        )
        paths = [target_rel or "."]  # git rejects "" as a pathspec
        if self._git.path_exists_at_ref(ref, pyproject_rel):
            paths.append(pyproject_rel)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            self._git.archive_paths(ref, paths, tmp_root)
            project_root = tmp_root / project_rel if project_rel else tmp_root
            scan_target = tmp_root / target_rel
            scanned = Scanner(scan_target, project_root).report
            # Rewire by_file keys from the tmp materialization's root onto
            # ``target`` itself -- both reports must key the same file the
            # same way, or every path looks unrelated to the other side.
            old, new = str(scan_target), str(target)
            if scan_target.is_dir():
                # Rebase whole segments; a "." target keys files as "pkg/a.py".
                old += "/"
                new = "" if new == "." else new.rstrip("/") + "/"
            return SuppressionReport.rebased(scanned, old, new)

    def text_at(self, ref: str, path: Path) -> str | None:
        """Return ``path``'s committed text at ``ref``, or ``None`` if absent."""
        rel = self.relpath(path)
        if not self._git.path_exists_at_ref(ref, rel):
            return None
        with tempfile.TemporaryDirectory() as tmp:
            self._git.archive_paths(ref, [rel], Path(tmp))
            return (Path(tmp) / rel).read_text()

    def relpath(self, path: Source) -> str:
        """Return ``path`` as a POSIX path relative to the git repository root.

        ``git archive``/``git cat-file`` pathspecs are always root-relative, so
        every path this class hands to :class:`GitRepo` must be converted here
        rather than used as given. The repo root itself rewrites to ``""``
        (not ``"."``, which git rejects) -- ``GitRepo.path_exists_at_ref``
        depends on that empty-string spelling for a root-relative probe.
        """
        git_root = self._git.root
        if git_root is None:
            msg = "not inside a git repository"
            raise GitError(msg)
        resolved = SourceSet.path(path).resolve()
        try:
            rel = resolved.relative_to(git_root.resolve())
        except ValueError as exc:
            msg = f"{resolved} is outside the git repository at {git_root}"
            raise GitError(msg) from exc
        rel_str = rel.as_posix()
        return "" if rel_str == "." else rel_str
