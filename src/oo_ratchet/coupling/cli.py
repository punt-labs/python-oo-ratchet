"""Command-line entry point: parse arguments and dispatch to the ratchet."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from oo_ratchet.source_set import Source, SourceSet

from .audit import CouplingAuditError
from .baseline import CouplingBaseline, CouplingBaselineError
from .bless import CouplingBless
from .config import CouplingConfig, CouplingConfigError
from .gitio import GitError, GitRepo
from .outcome import Outcome
from .ratchet import CouplingRatchet
from .report import CouplingReport
from .scorer import CouplingScorer
from .writer import CouplingWriter


@dataclass(frozen=True, slots=True)
class Options:
    """Parsed command-line options for one coupling ratchet invocation."""

    src: Source
    check: bool
    update: bool
    rebaseline: bool
    log: bool
    json: bool
    threshold: bool
    relax: str | None
    rebaseline_files: tuple[str, ...] | None
    justify: str
    reason: str
    base_ref: str | None
    require_base: bool
    allow_ci_write: bool
    source: str | None
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
            log=bool(ns.log),
            json=bool(ns.json),
            threshold=bool(ns.threshold),
            relax=ns.relax,
            rebaseline_files=cls._split_paths(ns.rebaseline_files),
            justify=ns.justify or "",
            reason=ns.reason or "",
            base_ref=ns.base_ref,
            require_base=bool(ns.require_base),
            allow_ci_write=bool(ns.allow_ci_write),
            source=ns.source,
            tripwire=bool(ns.tripwire),
        )

    @staticmethod
    def _split_paths(raw: str | None) -> tuple[str, ...] | None:
        """Split ``--rebaseline-files``' comma-joined value, or ``None`` if absent."""
        if raw is None:
            return None
        return tuple(p.strip() for p in raw.split(",") if p.strip())

    @staticmethod
    def _build_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="oo-ratchet coupling",
            description="module coupling/cohesion scorer and regression ratchet",
        )
        SourceSet.add(parser)
        # Exactly one action selects the operation; passing two is an argparse
        # error, not a silent first-wins pick.
        action = parser.add_mutually_exclusive_group()
        action.add_argument("--check", action="store_true", help="ratchet check")
        action.add_argument("--update", action="store_true", help="scoped update")
        action.add_argument("--rebaseline", action="store_true", help="reset baseline")
        action.add_argument("--threshold", action="store_true", help="per-file table")
        action.add_argument("--relax", metavar="FILE", help="relax one file's baseline")
        action.add_argument(
            "--rebaseline-files",
            metavar="PATH[,PATH...]",
            help="bounded scoped bless of named files, --reason required",
        )
        action.add_argument("--log", action="store_true", help="show audit history")
        action.add_argument("--json", action="store_true", help="emit JSON scores")
        parser.add_argument("--justify", default="", help="justification for --relax")
        parser.add_argument(
            "--reason",
            default="",
            help="justification for --rebaseline-files / --rebaseline",
        )
        parser.add_argument("--base-ref", metavar="REF", help="comparison base commit")
        parser.add_argument(
            "--require-base", action="store_true", help="fail if base unresolvable"
        )
        parser.add_argument(
            "--allow-ci-write", action="store_true", help="permit writes under CI"
        )
        parser.add_argument("--source", metavar="REF", help="audit source (PR/bead)")
        parser.add_argument(
            "--tripwire",
            action="store_true",
            help="post-merge push:[main] mode: an absent base baseline is the "
            "one-time adoption merge and bootstrap-passes",
        )
        return parser


class Cli:
    """Score the target and route the request to the ratchet or writer."""

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
        guard = self._rebaseline_files_guard()
        if guard is not None:
            return self._emit(guard)
        if not SourceSet.path(self._opts.src).exists():
            return self._emit(Outcome.failed(f"Not found: {self._opts.src}"))
        try:
            # Score inside the try: a read/decode failure (OSError,
            # UnicodeDecodeError) or a corrupt in-tree baseline must surface as a
            # clean non-zero, not a traceback.
            config = CouplingConfig.load(self._root)
            scorer = CouplingScorer(self._opts.src, self._root, config)
            action = self._run_action(scorer)
            outcome = action if action is not None else self._run_view(scorer)
        except (
            GitError,
            CouplingBaselineError,
            CouplingAuditError,
            CouplingConfigError,
            OSError,
            UnicodeDecodeError,
        ) as exc:
            outcome = Outcome.failed(f"FAIL: {exc}")
        return self._emit(outcome)

    def _rebaseline_files_guard(self) -> Outcome | None:
        """Reject an empty path list or blank ``--reason`` before scoring."""
        if self._opts.rebaseline_files is None:
            return None
        if not self._opts.rebaseline_files:
            return Outcome.failed("FAIL: --rebaseline-files requires at least one path")
        if not self._opts.reason.strip():
            return Outcome.failed("FAIL: --rebaseline-files requires --reason <text>")
        return None

    @staticmethod
    def _emit(outcome: Outcome) -> int:
        sys.stdout.writelines(line + "\n" for line in outcome.lines)
        return outcome.exit_code

    def _run_action(self, scorer: CouplingScorer) -> Outcome | None:
        opts = self._opts
        ratchet = CouplingRatchet(self._root, self._git)
        writer = CouplingWriter(self._root, self._git)
        if opts.check:
            return ratchet.check(
                scorer,
                base_ref=opts.base_ref,
                require_base=opts.require_base,
                tripwire=opts.tripwire,
            )
        if opts.rebaseline:
            return writer.rebaseline(
                scorer,
                allow_ci_write=opts.allow_ci_write,
                source=opts.source,
                reason=opts.reason,
            )
        if opts.relax is not None:
            return writer.relax(
                scorer,
                opts.relax,
                justify=opts.justify,
                allow_ci_write=opts.allow_ci_write,
                source=opts.source,
            )
        if opts.rebaseline_files is not None:
            return CouplingBless(self._root, self._git, scorer.config.caps).apply(
                CouplingBaseline.metrics_by_file(scorer.results),
                list(opts.rebaseline_files),
                reason=opts.reason,
                source=opts.source,
                allow_ci_write=opts.allow_ci_write,
                base_ref=opts.base_ref,
                require_base=opts.require_base,
            )
        if opts.update:
            return writer.update(
                scorer,
                base_ref=opts.base_ref,
                require_base=opts.require_base,
                allow_ci_write=opts.allow_ci_write,
                source=opts.source,
            )
        if opts.log:
            return ratchet.show_log()
        return None

    def _run_view(self, scorer: CouplingScorer) -> Outcome:
        report = CouplingReport(scorer)
        code = 1 if scorer.fail_count > 0 else 0
        if self._opts.json:
            return Outcome(code, (report.to_json(),))
        lines = [*report.render_table(), *report.render_packages()]
        if self._opts.threshold:
            lines.extend(report.render_per_file())
        return Outcome(code, tuple(lines))


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the coupling ratchet CLI, returning an exit code."""
    try:
        return Cli(Options.parse(argv)).run()
    except GitError as exc:  # raised while locating the repository root
        sys.stdout.write(f"FAIL: {exc}\n")
        return 1
