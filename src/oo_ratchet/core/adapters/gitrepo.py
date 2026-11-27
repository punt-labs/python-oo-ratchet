"""The one git adapter: implements ``History`` for every gate."""

from __future__ import annotations

import io
import logging
import subprocess
import tarfile
from collections.abc import Sequence
from pathlib import Path
from typing import Self

from oo_ratchet.core.domain.changes import Diff
from oo_ratchet.core.domain.errors import GitError
from oo_ratchet.core.domain.records import AuditRecord
from oo_ratchet.core.domain.scores import Rows

from .formats import AuditFormat, BaselineFormat

logger = logging.getLogger(__name__)

TIMEOUT = 10


class GitRepo:
    """Answer the gates' git questions, degrading to ``None`` outside a repo.

    A real git error raises ``GitError`` rather than reading as absence, so a
    gate never fails open on a broken git call.
    """

    _root: Path | None
    _baseline_file: str
    _audit_file: str

    def __new__(cls, start: Path, baseline_file: str, audit_file: str) -> Self:
        self = super().__new__(cls)
        out = cls._run(["git", "rev-parse", "--show-toplevel"], start)
        self._root = Path(out.strip()) if out is not None else None
        self._baseline_file = baseline_file
        self._audit_file = audit_file
        return self

    @property
    def root(self) -> Path | None:
        """Return the repository root, or ``None`` outside a repo."""
        return self._root

    def resolve(self, ref: str | None) -> str | None:
        """Return the comparison base: ``ref`` as a commit, else the merge base."""
        if ref is not None:
            out = self._git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"])
        else:
            out = self._git(["merge-base", "origin/main", "HEAD"])
        return out.strip() if out else None

    def head(self) -> str | None:
        """Return the abbreviated HEAD commit."""
        out = self._git(["rev-parse", "--short", "HEAD"])
        return out.strip() if out is not None else None

    def changes_since(self, base: str) -> Diff:
        """Return the files changed from ``base`` to the work tree, with renames."""
        out = self._git(["diff", "--name-status", "-M", base])
        if out is None:
            raise GitError(f"git diff against {base} failed")
        return Diff.from_name_status(out)

    def baseline_at(self, ref: str) -> Rows | None:
        """Return the baseline committed at ``ref``, ``None`` if it is absent."""
        text = self.show(ref, self._baseline_file)
        if text is None:
            return None
        return BaselineFormat.decode(text, f"{ref}:{self._baseline_file}")

    def audit_at(self, ref: str) -> tuple[AuditRecord, ...] | None:
        """Return the audit records committed at ``ref``, ``None`` if absent."""
        text = self.show(ref, self._audit_file)
        return None if text is None else AuditFormat.decode(text)

    def exists_at(self, ref: str, path: str) -> bool:
        """Return whether ``path`` is a blob or tree at ``ref``.

        ``git cat-file -e`` exits 128 both for "not in this tree" and for
        unrelated failures (a corrupt object, a bad ref spelling); only the
        former is absence. A blank ``path`` addresses the root tree.
        """
        root = self._need_root()
        spec = f"{ref}:{path}"
        try:
            result = subprocess.run(
                ["git", "cat-file", "-e", spec],
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
                cwd=root,
            )
        except (
            FileNotFoundError,
            subprocess.TimeoutExpired,
            UnicodeDecodeError,
        ) as exc:
            raise GitError(f"git cat-file -e {spec} failed to run: {exc}") from exc
        if result.returncode == 0:
            return True
        if self._absent(result.returncode, result.stderr):
            return False
        detail = result.stderr.strip().lower() or f"exit {result.returncode}"
        raise GitError(f"git cat-file -e {spec} errored: {detail}")

    def archive_paths(self, ref: str, paths: Sequence[str], dest: Path) -> None:
        """Materialize ``paths`` as they existed at ``ref`` into ``dest``.

        One ``git archive``, extracted in-process. Callers pass only paths
        present at ``ref`` (``exists_at``): ``git archive`` errors on a
        pathspec that matches nothing.
        """
        root = self._need_root()
        if not paths:
            return
        try:
            archive = subprocess.run(
                ["git", "archive", ref, "--", *paths],
                capture_output=True,
                timeout=TIMEOUT,
                cwd=root,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise GitError(f"git archive {ref} failed to run: {exc}") from exc
        if archive.returncode != 0:
            detail = archive.stderr.decode(errors="replace").strip()
            raise GitError(
                f"git archive {ref} errored: {detail or f'exit {archive.returncode}'}"
            )
        try:
            with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
                # The "data" filter (PEP 706) refuses links, devices and any
                # member that escapes ``dest``.
                tar.extractall(dest, filter="data")
        except (tarfile.TarError, OSError) as exc:
            raise GitError(f"tar extraction of {ref} archive failed: {exc}") from exc

    def _need_root(self) -> Path:
        if self._root is None:
            raise GitError("not inside a git repository")
        return self._root

    def _git(self, args: list[str]) -> str | None:
        if self._root is None:
            return None  # not in a repo: never run against the ambient CWD
        return self._run(["git", "-c", "core.quotePath=false", *args], self._root)

    @staticmethod
    def _run(args: list[str], cwd: Path) -> str | None:
        try:
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=TIMEOUT, cwd=cwd
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning("git did not run (%s); treating it as unavailable", exc)
            return None
        except UnicodeDecodeError as exc:
            raise GitError(f"git output is not valid UTF-8: {exc}") from exc
        return result.stdout if result.returncode == 0 else None

    def show(self, ref: str, path: str) -> str | None:
        """Return ``git show ref:path``, ``None`` only when the path is absent."""
        if self._root is None:
            return None
        try:
            result = subprocess.run(
                ["git", "show", f"{ref}:{path}"],
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
                cwd=self._root,
            )
        except (
            FileNotFoundError,
            subprocess.TimeoutExpired,
            UnicodeDecodeError,
        ) as exc:
            raise GitError(f"git show {ref}:{path} failed to run: {exc}") from exc
        if result.returncode == 0:
            return result.stdout
        if self._absent(result.returncode, result.stderr):
            return None
        detail = result.stderr.strip() or f"exit {result.returncode}"
        raise GitError(f"git show {ref}:{path} errored: {detail}")

    @staticmethod
    def _absent(returncode: int, stderr: str) -> bool:
        lowered = stderr.lower()
        return returncode == 128 and (
            "does not exist in" in lowered or "exists on disk, but not in" in lowered
        )
