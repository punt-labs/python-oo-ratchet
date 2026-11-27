"""Aggregate per-file suppression counts into a whole-tree report."""

from __future__ import annotations

import json
from typing import Self

from oo_ratchet.core.domain.tallies import Tally

from .patterns import CATEGORIES, PATTERN_NAMES, FileSuppressions


class SuppressionReport:
    """Render a ``Tally`` of suppression counts as text or JSON."""

    _tally: Tally

    def __new__(cls, tally: Tally) -> Self:
        self = super().__new__(cls)
        self._tally = tally
        return self

    @classmethod
    def from_files(
        cls,
        file_results: list[FileSuppressions],
        per_file_ignores_count: int,
        per_file_ignores_breakdown: dict[str, int] | None = None,
    ) -> Self:
        """Aggregate per-file counts and the pyproject ignores into a report."""
        by_category = dict.fromkeys(CATEGORIES, 0)
        by_category["per_file_ignores"] = per_file_ignores_count
        by_file: dict[str, dict[str, int]] = {}
        for fs in file_results:
            for name in PATTERN_NAMES:
                by_category[name] += fs.count(name)
            if fs.total > 0:
                by_file[fs.path] = fs.to_dict()
        # Per-file-ignores entries are keyed by their literal pyproject.toml
        # pattern -- a repo-relative path on both the current and any
        # rescanned-at-ref side, so (unlike source-file keys) they never need
        # rebasing onto a different filesystem root. Folding them into
        # by_file is what lets a regression report name the actual
        # pyproject.toml entry responsible for a count rise, instead of
        # hiding it inside an aggregate category total with no location.
        for pattern, count in (per_file_ignores_breakdown or {}).items():
            if count > 0:
                by_file.setdefault(pattern, {})["per_file_ignores"] = count
        return cls(Tally(by_category, by_file))

    @property
    def tally(self) -> Tally:
        """Return the counts the gate compares."""
        return self._tally

    @property
    def total(self) -> int:
        """Return the total suppression count across all files and config."""
        return self._tally.total

    @property
    def by_category(self) -> dict[str, int]:
        """Return the suppression count per category."""
        return dict(self._tally.by_category)

    @property
    def by_file(self) -> dict[str, dict[str, int]]:
        """Return the non-zero suppression counts per file."""
        return {path: dict(counts) for path, counts in self._tally.by_file.items()}

    def rebased(self, old_prefix: str, new_prefix: str) -> Self:
        """Return the report with its per-file keys moved onto a new root.

        The tally owns the rule (``Tally.rebased``); the report only wraps it.
        """
        return type(self)(self._tally.rebased(old_prefix, new_prefix))

    def to_json(self) -> str:
        """Return the report as machine-readable JSON."""
        return json.dumps(
            {
                "total": self.total,
                "by_category": self._tally.by_category,
                "by_file": self._tally.by_file,
            },
            indent=2,
        )

    def render(self) -> list[str]:
        """Return the human-readable summary as report lines."""
        lines = [
            f"\nTotal suppressions: {self.total}",
            f"\n{'Category':<20} {'Count':>6}",
            "-" * 28,
        ]
        lines.extend(
            f"{category:<20} {count:>6}"
            for category, count in sorted(self._tally.by_category.items())
        )
        return lines

    def render_threshold(self) -> list[str]:
        """Return the per-file breakdown as report lines."""
        lines = ["\n--- Per-file breakdown ---"]
        if not self._tally.by_file:
            lines.append("  (no suppressions found)")
            return lines
        for fpath in sorted(self._tally.by_file):
            counts = self._tally.by_file[fpath]
            lines.append(f"\n  {fpath}  (total: {sum(counts.values())})")
            lines.extend(
                f"    {cat:<20} {count:>4}" for cat, count in sorted(counts.items())
            )
        return lines
