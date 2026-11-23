"""Run a git listing command and return its NUL-separated paths exactly."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from oo_ratchet.coupling.gitio import GitError

_TIMEOUT = 10


class NulListing:
    """Read ``git ... -z`` output as bytes, so no path byte is translated.

    Text-mode reads turn a carriage return into a line feed, which would make a
    directory with one look like a different directory. Any failure raises
    ``GitError``; a listing is never read as empty because git failed.
    """

    @staticmethod
    def run(root: Path, args: list[str]) -> list[str]:
        """Return the paths ``git <args> -z`` prints, run from ``root``."""
        command = ["git", "-c", "core.quotePath=false", *args]
        try:
            done = subprocess.run(
                command, capture_output=True, timeout=_TIMEOUT, cwd=root, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            msg = f"git {args[0]} did not run: {exc}"
            raise GitError(msg) from exc
        if done.returncode != 0:
            msg = (
                f"git {args[0]} failed: {done.stderr.decode(errors='replace').strip()}"
            )
            raise GitError(msg)
        return [os.fsdecode(raw) for raw in done.stdout.split(b"\0") if raw]
