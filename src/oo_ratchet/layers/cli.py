"""Command-line entry point: parse arguments and dispatch to the ratchet."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from oo_ratchet.coupling.gitio import GitError
from oo_ratchet.coupling.outcome import Outcome
from oo_ratchet.design.layer_config import LayerConfigError

from .baseline import LayersBaselineError
from .gitio import LayersGit
from .ratchet import LayersRatchet
from .report import LayersReport
from .scan import LayerScan, LayersScanError
from .writer import LayersWriter


@dataclass(frozen=True, slots=True)
class Options:
    """Parsed command-line options for one layers ratchet invocation."""

    src: Path
    check: bool
    update: bool
    json: bool
    base_ref: str | None
    require_base: bool
    allow_ci_write: bool
    source: str | None
    tripwire: bool

    @classmethod
    def parse(cls, argv: list[str] | None = None) -> Self:
        """Build options from ``argv`` (defaults to ``sys.argv``)."""
        ns = cls._build_parser().parse_args(argv)
        return cls(
            src=Path(ns.src),
            check=bool(ns.check),
            update=bool(ns.update),
            json=bool(ns.json),
            base_ref=ns.base_ref,
            require_base=bool(ns.require_base),
            allow_ci_write=bool(ns.allow_ci_write),
            source=ns.source,
            tripwire=bool(ns.tripwire),
        )

    @staticmethod
    def _build_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="oo-ratchet layers",
            description="package layer contract: imports only point down the layers",
        )
        parser.add_argument("src", help="the package directory to scan (src/pkg)")
        action = parser.add_mutually_exclusive_group()
        action.add_argument("--check", action="store_true", help="ratchet check")
        action.add_argument(
            "--update",
            action="store_true",
            help="adopt the first baseline, then shrink it; never adds a violation",
        )
        action.add_argument("--json", action="store_true", help="emit JSON report")
        parser.add_argument(
            "--base-ref", metavar="REF", help="comparison base commit (--check)"
        )
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
    """Scan the package and route the request to the ratchet, writer or report."""

    _opts: Options
    _git: LayersGit
    _root: Path

    def __new__(cls, options: Options) -> Self:
        self = super().__new__(cls)
        self._opts = options
        self._git = LayersGit()
        self._root = self._git.root or Path.cwd()
        return self

    def run(self) -> int:
        """Execute the requested operation and return its exit code."""
        if not self._opts.src.exists():
            return self._emit(Outcome.failed(f"Not found: {self._opts.src}"))
        try:
            scan = LayerScan(self._opts.src)
            outcome = self._dispatch(scan)
        except (
            GitError,
            LayersBaselineError,
            LayerConfigError,
            LayersScanError,
            OSError,
            UnicodeDecodeError,
        ) as exc:
            outcome = Outcome.failed(f"FAIL: {exc}")
        return self._emit(outcome)

    def _dispatch(self, scan: LayerScan) -> Outcome:
        opts = self._opts
        if opts.check:
            return LayersRatchet(self._root, self._git).check(
                scan,
                base_ref=opts.base_ref,
                require_base=opts.require_base,
                tripwire=opts.tripwire,
            )
        if opts.update:
            return LayersWriter(self._root, self._git).update(
                scan, allow_ci_write=opts.allow_ci_write, source=opts.source
            )
        report = LayersReport(scan)
        if opts.json:
            return Outcome.passed(report.to_json())
        return Outcome.passed(*report.render())

    @staticmethod
    def _emit(outcome: Outcome) -> int:
        for line in outcome.lines:
            sys.stdout.write(line + "\n")
        return outcome.exit_code


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the layers ratchet CLI, returning an exit code."""
    try:
        return Cli(Options.parse(argv)).run()
    except GitError as exc:  # raised while locating the repository root
        sys.stdout.write(f"FAIL: {exc}\n")
        return 1
