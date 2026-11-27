"""Command-line entry point: parse arguments and dispatch to the ratchet."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from oo_ratchet.core.adapters.tallygate import GateFiles, TallyGate
from oo_ratchet.core.domain.errors import StateError
from oo_ratchet.core.domain.tallies import Tally
from oo_ratchet.source_set import Source, SourceSet

from .pyproject import PyprojectError
from .report import SuppressionReport
from .scanner import Scanner

_FILES = GateFiles(
    ".suppression-baseline.json",
    ".suppression-audit.jsonl",
    ".suppression-relax.json",
)


@dataclass(frozen=True, slots=True)
class SuppressionOptions:
    """Parsed command-line options for one suppression ratchet invocation."""

    src: Source
    check: bool
    update: bool
    rebaseline: bool
    json: bool
    threshold: bool
    relax: str | None
    justify: str
    reason: str
    source: str | None
    base_ref: str | None
    require_base: bool
    allow_ci_write: bool
    tripwire: bool

    @property
    def writes(self) -> bool:
        """Return whether the request writes the baseline or the ledger."""
        return self.update or self.rebaseline or self.relax is not None

    @classmethod
    def parse(cls, argv: list[str] | None = None) -> Self:
        """Build options from ``argv`` (defaults to ``sys.argv``)."""
        ns = SourceSet.parse(cls._build_parser(), argv)
        return cls(
            src=ns.src,
            check=bool(ns.check),
            update=bool(ns.update),
            rebaseline=bool(ns.rebaseline),
            json=bool(ns.json),
            threshold=bool(ns.threshold),
            relax=ns.relax,
            justify=ns.justify or "",
            reason=ns.reason or "",
            source=ns.source,
            base_ref=ns.base_ref,
            require_base=bool(ns.require_base),
            allow_ci_write=bool(ns.allow_ci_write),
            tripwire=bool(ns.tripwire),
        )

    @staticmethod
    def _build_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="oo-ratchet suppressions",
            description="count lint/type suppressions and enforce a ratchet",
        )
        SourceSet.add(parser)
        action = parser.add_mutually_exclusive_group()
        action.add_argument("--check", action="store_true", help="ratchet check")
        action.add_argument("--update", action="store_true", help="update baseline")
        action.add_argument(
            "--rebaseline",
            action="store_true",
            help="audited reset to current counts (may raise), --reason required",
        )
        action.add_argument("--threshold", action="store_true", help="per-file table")
        action.add_argument("--json", action="store_true", help="emit JSON counts")
        action.add_argument("--relax", metavar="FILE", help="waive one file's rise")
        parser.add_argument("--justify", default="", help="justification for --relax")
        parser.add_argument("--reason", default="", help="reason for --rebaseline")
        parser.add_argument(
            "--source", metavar="REF", help="PR/issue recorded in the audit entry"
        )
        parser.add_argument("--base-ref", metavar="REF", help="comparison base commit")
        parser.add_argument(
            "--require-base", action="store_true", help="fail if base unresolvable"
        )
        parser.add_argument(
            "--allow-ci-write", action="store_true", help="permit writes under CI"
        )
        parser.add_argument(
            "--tripwire",
            action="store_true",
            help="post-merge push:[main] mode: an absent base baseline is the "
            "one-time adoption merge and bootstrap-passes",
        )
        return parser


class SuppressionCommand:
    """Scan the target and route the request to the ratchet or a view."""

    _opts: SuppressionOptions
    _gate: TallyGate

    def __new__(cls, options: SuppressionOptions) -> Self:
        self = super().__new__(cls)
        self._opts = options
        self._gate = TallyGate(_FILES, options.src, cls._count)
        return self

    def run(self) -> int:
        """Execute the requested operation and return its exit code."""
        if not SourceSet.path(self._opts.src).exists():
            return self._emit([f"not found: {self._opts.src}"], 1)
        try:
            # Anchor the scan's project root and the state files to the repo
            # root, not cwd, so running from a subdirectory still reads the
            # right pyproject.toml and baseline. Scan and read the state inside
            # the try: an unreadable .py file or a corrupt baseline or ledger
            # must surface as a clean non-zero, not a traceback.
            report = Scanner(self._opts.src, self._gate.root).report
            self._gate.prepare()
            lines, code = self._dispatch(report)
        except (StateError, PyprojectError, OSError, UnicodeDecodeError) as exc:
            lines, code = [f"FAIL: {exc}"], 1
        return self._emit(lines, code)

    def _dispatch(self, report: SuppressionReport) -> tuple[list[str], int]:
        opts = self._opts
        tally = self._count_report(report)
        if opts.check:
            return self._gate.check(
                tally,
                base_ref=opts.base_ref,
                require_base=opts.require_base,
                tripwire=opts.tripwire,
            )
        if opts.writes:
            return self._write(tally)
        if opts.json:
            return [report.to_json()], 0
        lines = list(report.render())
        if opts.threshold:
            lines.extend(report.render_threshold())
        return lines, 0

    def _write(self, tally: Tally) -> tuple[list[str], int]:
        opts = self._opts
        if opts.update:
            return self._gate.update(tally, allow_ci_write=opts.allow_ci_write)
        if opts.rebaseline:
            return self._gate.rebaseline(
                tally,
                reason=opts.reason,
                source=opts.source,
                allow_ci_write=opts.allow_ci_write,
            )
        return self._gate.relax(
            tally,
            base_ref=opts.base_ref,
            file=opts.relax or "",
            justify=opts.justify,
            allow_ci_write=opts.allow_ci_write,
        )

    @staticmethod
    def _count(target: Source, project: Path) -> Tally:
        return SuppressionCommand._count_report(Scanner(target, project).report)

    @staticmethod
    def _count_report(report: SuppressionReport) -> Tally:
        return report.tally

    @staticmethod
    def _emit(lines: list[str], code: int) -> int:
        sys.stdout.writelines(line + "\n" for line in lines)
        return code


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the suppression ratchet CLI, returning a code."""
    return SuppressionCommand(SuppressionOptions.parse(argv)).run()
