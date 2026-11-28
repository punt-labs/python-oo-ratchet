"""Score a file or directory of modules: read the files, feed ``Scoring``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Self

from oo_ratchet.source_set import Source, SourceSelection

from .metrics import ModuleMetrics
from .scoring import Scoring


class Scorer(Scoring):
    """Score modules against OO quality thresholds.

    Keys are normalized repo-relative (POSIX) against ``repo_root`` so that
    scorer output, baseline keys, and git diff paths all intersect cleanly
    regardless of how the target path was spelled on the command line.
    """

    def __new__(cls, target: Source, repo_root: Path | None = None) -> Self:
        root = repo_root if repo_root is not None else Path.cwd()
        return super().__new__(
            cls, [cls._score_or_error(p, root) for p in SourceSelection(target).files()]
        )

    @staticmethod
    def _normalize(path: Path, root: Path) -> str:
        resolved = path.resolve()
        try:
            return resolved.relative_to(root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()

    @classmethod
    def _score_file(cls, path: Path, root: Path) -> dict[str, float | int | str]:
        source = path.read_text(encoding="utf-8")
        return ModuleMetrics(cls._normalize(path, root), source).compute()

    @classmethod
    def _score_or_error(cls, path: Path, root: Path) -> dict[str, float | int | str]:
        try:
            return cls._score_file(path, root)
        except (SyntaxError, UnicodeDecodeError, OSError) as e:
            return {"file": cls._normalize(path, root), "error": str(e)}

    def to_json(self) -> str:
        """Return per-file, aggregate, grades, and thresholds as JSON."""
        return json.dumps(self.report(), indent=2)
