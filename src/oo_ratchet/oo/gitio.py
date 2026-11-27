"""Git queries the design shadow check needs: refs, merge bases and diffs."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Self

from .diffmodel import Diff

logger = logging.getLogger(__name__)

_TIMEOUT = 10


class GitError(Exception):
    """A git command the shadow check depends on failed.

    Raised so a check fails closed: a failed ``git diff`` is never "no changes".
    """


class GitRepo:
    """Answer the shadow check's git questions, or degrade to ``None`` outside git."""

    _root: Path | None

    def __new__(cls, start: Path | None = None) -> Self:
        self = super().__new__(cls)
        self._root = cls._discover_root(start if start is not None else Path.cwd())
        return self

    @property
    def root(self) -> Path | None:
        """Return the repository root, or ``None`` when not inside a repo."""
        return self._root

    @classmethod
    def _discover_root(cls, start: Path) -> Path | None:
        out = cls._run(["git", "rev-parse", "--show-toplevel"], cwd=start)
        return Path(out.strip()) if out is not None else None

    @staticmethod
    def _run(
        args: list[str], cwd: Path | None, *, timeout: float = _TIMEOUT
    ) -> str | None:
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning("git did not run (%s); treating it as unavailable", exc)
            return None
        except UnicodeDecodeError as exc:
            raise GitError(f"git output is not valid UTF-8: {exc}") from exc
        if result.returncode != 0:
            return None
        return result.stdout

    def _git(self, args: list[str], *, timeout: float = _TIMEOUT) -> str | None:
        if self._root is None:
            return None  # not in a repo: degrade, never run against the ambient CWD
        return self._run(
            ["git", "-c", "core.quotePath=false", *args],
            cwd=self._root,
            timeout=timeout,
        )

    def resolve_ref(self, ref: str) -> str | None:
        """Return the full commit hash for a ref, or ``None`` if unresolvable."""
        out = self._git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"])
        return out.strip() if out else None

    def merge_base(self, left: str, right: str) -> str | None:
        """Return the merge-base commit of two refs, or ``None``."""
        out = self._git(["merge-base", left, right])
        return out.strip() if out else None

    def diff(self, base: str) -> Diff:
        """Return files changed from ``base`` to the work tree, with renames."""
        out = self._git(["diff", "--name-status", "-M", base])
        if out is None:
            msg = f"git diff against {base} failed"
            raise GitError(msg)
        return Diff.from_name_status(out)
