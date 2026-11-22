"""Render design findings as an advisory text report or JSON."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Self

from .findings import Finding, Rules


class DesignReport:
    """Group findings by rule, with counts and the most-flagged files."""

    _findings: list[Finding]
    _skipped: list[Path]
    _files: int

    def __new__(cls, findings: list[Finding], skipped: list[Path], files: int) -> Self:
        self = super().__new__(cls)
        self._findings = sorted(findings, key=lambda f: (f.rule, f.path, f.line))
        self._skipped = skipped
        self._files = files
        return self

    def counts(self) -> dict[str, int]:
        """Return the number of findings per rule, every rule listed."""
        tally = Counter(f.rule for f in self._findings)
        return {rule: tally[rule] for rule in Rules.ordered()}

    def to_json(self) -> str:
        """Return the report as a JSON document."""
        return json.dumps(
            {
                "advisory": True,
                "files_scanned": self._files,
                "counts": self.counts(),
                "findings": [f.as_dict() for f in self._findings],
                "skipped": [str(p) for p in self._skipped],
            },
            indent=2,
        )

    def to_text(self) -> str:
        """Return the report as grouped, human-readable lines."""
        lines = [
            (
                f"oo-ratchet design (advisory, never fails): {len(self._findings)} "
                f"finding(s) in {self._files} file(s)"
            ),
        ]
        for rule, count in self.counts().items():
            lines.append(f"\n{rule} ({count}): {Rules.DESCRIPTIONS[rule]}")
            lines.extend(
                f"  {f.path}:{f.line}  {f.symbol}  -- {f.detail}"
                for f in self._findings
                if f.rule == rule
            )
        lines.extend(f"\nskipped (unparseable): {p}" for p in self._skipped)
        return "\n".join(lines) + "\n"
