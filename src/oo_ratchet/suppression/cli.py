"""Command-line entry point: parse arguments and dispatch to the ratchet."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Self

from oo_ratchet.core.adapters.gatecli import GateCli
from oo_ratchet.core.adapters.gitrepo import GitRepo as CoreGit
from oo_ratchet.core.adapters.tallycli import TallyCli
from oo_ratchet.core.adapters.tallyfiles import (
    JsonLedger,
    JsonTallyStore,
    TallyAuditFile,
)
from oo_ratchet.core.adapters.tallyrepo import TallyRepo
from oo_ratchet.core.application.tallyops import (
    TallyCheck,
    TallyRebaseline,
    TallyRelax,
    TallyUpdate,
)
from oo_ratchet.core.application.tallyports import TallyPorts
from oo_ratchet.core.domain.errors import StateError
from oo_ratchet.core.domain.tallies import Tally
from oo_ratchet.core.domain.verdicts import Verdict
from oo_ratchet.source_set import Source, SourceSet

from .baseline import SuppressionBaseline, SuppressionBaselineError
from .gitio import GitError, GitRepo
from .outcome import Outcome
from .pyproject import PyprojectError
from .relax import SuppressionRelaxError
from .report import SuppressionReport
from .scanner import Scanner


@dataclass(frozen=True, slots=True)
class Options:
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


class Cli:
    """Scan the target and route the request to the ratchet or a view."""

    _opts: Options
    _git: GitRepo
    _root: Path

    def __new__(cls, options: Options) -> Self:
        self = super().__new__(cls)
        self._opts = options
        self._git = GitRepo()
        self._root = self._git.root or Path.cwd()
        return self

    def run(self) -> int:
        """Execute the requested operation and return its exit code."""
        if not SourceSet.path(self._opts.src).exists():
            return self._emit(Outcome.failed(f"not found: {self._opts.src}"))
        try:
            # Anchor the scan's project root and the baseline path to the repo
            # root (via GitRepo), not cwd, so running from a subdirectory still
            # reads the right pyproject.toml and .suppression-baseline.json.
            # Scan and construct inside the try: an unreadable .py file (OSError)
            # or a corrupt in-tree baseline (eager load) must surface as a clean
            # non-zero, not a traceback.
            report = Scanner(self._opts.src, self._root).report
            outcome = self._dispatch(SuppressionBaseline(self._root), report)
        except (
            GitError,
            SuppressionBaselineError,
            SuppressionRelaxError,
            PyprojectError,
            OSError,
            UnicodeDecodeError,
        ) as exc:
            outcome = Outcome.failed(f"FAIL: {exc}")
        return self._emit(outcome)

    def _dispatch(
        self, baseline: SuppressionBaseline, report: SuppressionReport
    ) -> Outcome:
        opts = self._opts
        if opts.check:
            return baseline.check(
                report,
                target=opts.src,
                base_ref=opts.base_ref,
                require_base=opts.require_base,
                tripwire=opts.tripwire,
            )
        if opts.update:
            return baseline.update(report, allow_ci_write=opts.allow_ci_write)
        if opts.rebaseline:
            return baseline.rebaseline(
                report,
                reason=opts.reason,
                source=opts.source,
                allow_ci_write=opts.allow_ci_write,
            )
        if opts.relax is not None:
            return baseline.relax(
                report,
                target=opts.src,
                base_ref=opts.base_ref,
                file=opts.relax,
                justify=opts.justify,
                allow_ci_write=opts.allow_ci_write,
            )
        if opts.json:
            return Outcome.passed(report.to_json())
        lines = list(report.render())
        if opts.threshold:
            lines.extend(report.render_threshold())
        return Outcome.passed(*lines)

    @staticmethod
    def _emit(outcome: Outcome) -> int:
        sys.stdout.writelines(line + "\n" for line in outcome.lines)
        return outcome.exit_code


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the suppression ratchet CLI, returning a code."""
    return Cli(Options.parse(argv)).run()


class CoreCli:
    """Scan the target and route the request through the shared core."""

    BASELINE: ClassVar[str] = ".suppression-baseline.json"
    AUDIT: ClassVar[str] = ".suppression-audit.jsonl"
    LEDGER: ClassVar[str] = ".suppression-relax.json"

    _opts: Options
    _root: Path
    _git: CoreGit

    def __new__(cls, options: Options) -> Self:
        self = super().__new__(cls)
        self._opts = options
        self._git = CoreGit(Path.cwd(), cls.BASELINE, cls.AUDIT)
        self._root = self._git.root or Path.cwd()
        return self

    def run(self) -> int:
        """Execute the requested operation and return its exit code."""
        if not SourceSet.path(self._opts.src).exists():
            return self._emit([f"not found: {self._opts.src}"], 1)
        try:
            # Scan and build the ports inside the try: an unreadable .py file,
            # a corrupt in-tree baseline or ledger (both read when built) must
            # surface as a clean non-zero, not a traceback.
            report = Scanner(self._opts.src, self._root).report
            lines, code = self._dispatch(report)
        except (StateError, PyprojectError, OSError, UnicodeDecodeError) as exc:
            lines, code = [f"FAIL: {exc}"], 1
        return self._emit(lines, code)

    def _dispatch(self, report: SuppressionReport) -> tuple[list[str], int]:
        opts = self._opts
        ports = self._ports()
        views = TallyCli(self.LEDGER)
        if opts.check:
            return self._verdict(
                views,
                TallyCheck(ports).run(
                    report.tally,
                    base_ref=opts.base_ref,
                    require_base=opts.require_base,
                    tripwire=opts.tripwire,
                ),
            )
        write = self._write(views, report.tally, ports)
        if write is not None:
            return write
        if opts.json:
            return [report.to_json()], 0
        lines = list(report.render())
        if opts.threshold:
            lines.extend(report.render_threshold())
        return lines, 0

    def _write(
        self, views: TallyCli, tally: Tally, ports: TallyPorts
    ) -> tuple[list[str], int] | None:
        opts = self._opts
        if not (opts.update or opts.rebaseline or opts.relax is not None):
            return None
        blocked = GateCli.write_blocked(allow_ci_write=opts.allow_ci_write)
        if blocked is not None:
            return self._verdict(views, blocked)
        if opts.update:
            return self._verdict(views, TallyUpdate(ports).run(tally))
        if opts.rebaseline:
            rebaseline = TallyRebaseline(ports)
            verdict = rebaseline.run(tally, reason=opts.reason, source=opts.source)
            return self._verdict(views, verdict)
        relax = TallyRelax(ports).run(
            tally,
            target=str(opts.src),
            base_ref=opts.base_ref,
            file=opts.relax or "",
            justify=opts.justify,
        )
        return self._verdict(views, relax)

    def _ports(self) -> TallyPorts:
        history = TallyRepo(
            self._git, self._opts.src, self._root, self._scan, self.LEDGER
        )
        return TallyPorts(
            history,
            JsonTallyStore(self._root / self.BASELINE),
            JsonLedger(self._root / self.LEDGER),
            TallyAuditFile(self._root / self.AUDIT),
        )

    @staticmethod
    def _scan(target: Source, project: Path) -> Tally:
        return Scanner(target, project).report.tally

    @staticmethod
    def _verdict(views: TallyCli, verdict: Verdict) -> tuple[list[str], int]:
        return views.text(verdict), views.exit_code(verdict)

    @staticmethod
    def _emit(lines: list[str], code: int) -> int:
        sys.stdout.writelines(line + "\n" for line in lines)
        return code


def core_main(argv: list[str] | None = None) -> int:
    """Run the suppression ratchet CLI on the shared core, returning a code."""
    return CoreCli(Options.parse(argv)).run()
