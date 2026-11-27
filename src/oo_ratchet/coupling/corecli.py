"""Command-line entry point: parse arguments and dispatch to the gate."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Self

from oo_ratchet.core.adapters.metricgate import MetricFiles, MetricGate
from oo_ratchet.core.domain.errors import StateError
from oo_ratchet.source_set import Source, SourceSet

from .config import CouplingConfig, CouplingConfigError
from .report import CouplingReport
from .scorer import CouplingScorer

_FILES = MetricFiles(".oo-coupling-baseline.json", ".oo-coupling-audit.jsonl")
_GUARDS = {
    "paths": "FAIL: --rebaseline-files requires at least one path",
    "reason": "FAIL: --rebaseline-files requires --reason <text>",
}


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


Report = tuple[list[str], int]


class Cli:
    """Score the target and route the request to the gate or a view."""

    _opts: Options
    _gate: MetricGate

    def __new__(cls, options: Options) -> Self:
        self = super().__new__(cls)
        self._opts = options
        self._gate = MetricGate(_FILES)
        return self

    def run(self) -> int:
        """Execute the requested operation and return its exit code."""
        guard = self._rebaseline_files_guard()
        if guard is not None:
            return self._emit([guard], 1)
        if not SourceSet.path(self._opts.src).exists():
            return self._emit([f"Not found: {self._opts.src}"], 1)
        try:
            # Score inside the try: a read/decode failure (OSError,
            # UnicodeDecodeError) or a corrupt in-tree baseline must surface as a
            # clean non-zero, not a traceback.
            config = CouplingConfig.load(self._gate.root)
            scorer = CouplingScorer(self._opts.src, self._gate.root, config)
            self._gate.prepare(config.policy(), scorer.measurement)
            lines, code = self._dispatch(scorer)
        except (StateError, CouplingConfigError, OSError, UnicodeDecodeError) as exc:
            lines, code = [f"FAIL: {exc}"], 1
        return self._emit(lines, code)

    def _rebaseline_files_guard(self) -> str | None:
        """Reject an empty path list or blank ``--reason`` before scoring."""
        if self._opts.rebaseline_files is None:
            return None
        if not self._opts.rebaseline_files:
            return _GUARDS["paths"]
        if not self._opts.reason.strip():
            return _GUARDS["reason"]
        return None

    @staticmethod
    def _emit(lines: list[str], code: int) -> int:
        sys.stdout.writelines(line + "\n" for line in lines)
        return code

    def _dispatch(self, scorer: CouplingScorer) -> Report:
        opts = self._opts
        if opts.check:
            return self._gate.check(
                base_ref=opts.base_ref,
                require_base=opts.require_base,
                tripwire=opts.tripwire,
            )
        if opts.log:
            return self._gate.log()
        if (
            opts.update
            or opts.rebaseline
            or opts.relax is not None
            or opts.rebaseline_files is not None
        ):
            return self._write()
        return self._view(scorer)

    def _write(self) -> Report:
        opts = self._opts
        gate = self._gate
        if opts.rebaseline:
            return gate.rebaseline(
                reason=opts.reason,
                allow_ci_write=opts.allow_ci_write,
                source=opts.source,
            )
        if opts.relax is not None:
            return gate.relax(
                opts.relax,
                justify=opts.justify,
                allow_ci_write=opts.allow_ci_write,
                source=opts.source,
            )
        if opts.rebaseline_files is not None:
            return gate.bless(
                list(opts.rebaseline_files),
                reason=opts.reason,
                allow_ci_write=opts.allow_ci_write,
                source=opts.source,
                base_ref=opts.base_ref,
                require_base=opts.require_base,
            )
        return gate.update(
            base_ref=opts.base_ref,
            require_base=opts.require_base,
            allow_ci_write=opts.allow_ci_write,
            source=opts.source,
        )

    def _view(self, scorer: CouplingScorer) -> Report:
        report = CouplingReport(scorer)
        code = 1 if scorer.fail_count > 0 else 0
        if self._opts.json:
            return [report.to_json()], code
        lines = [*report.render_table(), *report.render_packages()]
        if self._opts.threshold:
            lines.extend(report.render_per_file())
        return lines, code


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the coupling ratchet CLI, returning an exit code."""
    try:
        return Cli(Options.parse(argv)).run()
    except StateError as exc:  # raised while locating the repository root
        sys.stdout.write(f"FAIL: {exc}\n")
        return 1
