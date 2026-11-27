"""Command-line entry point: parse arguments and dispatch to the ratchet."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Self

from oo_ratchet.core.adapters.edgegate import EdgeGate
from oo_ratchet.core.adapters.gitrepo import GitRepo
from oo_ratchet.core.domain.errors import StateError
from oo_ratchet.coupling.outcome import Outcome
from oo_ratchet.source_set import Source, SourceSet

from .failures import FAILURES
from .report import LayersReport
from .scan import LayerScan
from .suggest import Suggestion


@dataclass(frozen=True, slots=True)
class Options:
    """Parsed command-line options for one layers ratchet invocation."""

    src: Source
    check: bool
    update: bool
    json: bool
    base_ref: str | None
    require_base: bool
    allow_ci_write: bool
    source: str | None
    tripwire: bool
    allow_config_change: bool
    suggest: bool

    @classmethod
    def parse(cls, argv: list[str] | None = None) -> Self:
        """Build options from ``argv`` (defaults to ``sys.argv``)."""
        parser = cls._build_parser()
        ns = SourceSet.parse(parser, argv)
        cls._validate(parser, ns)
        return cls(
            src=ns.src,
            check=bool(ns.check),
            update=bool(ns.update),
            json=bool(ns.json),
            base_ref=ns.base_ref,
            require_base=bool(ns.require_base),
            allow_ci_write=bool(ns.allow_ci_write),
            source=ns.source,
            tripwire=bool(ns.tripwire),
            allow_config_change=bool(ns.allow_config_change),
            suggest=bool(ns.suggest),
        )

    @classmethod
    def _validate(cls, parser: argparse.ArgumentParser, ns: argparse.Namespace) -> None:
        if not ns.check and cls._base_flags(ns):
            parser.error("--base-ref, --require-base and --tripwire need --check")
        if ns.allow_config_change and not (ns.check or ns.update):
            parser.error("--allow-config-change needs --check or --update")

    @staticmethod
    def _base_flags(ns: argparse.Namespace) -> bool:
        return ns.base_ref is not None or bool(ns.require_base) or bool(ns.tripwire)

    @staticmethod
    def _build_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="oo-ratchet layers",
            description="package layer contract: imports only point down the layers",
        )
        SourceSet.add(parser)
        action = parser.add_mutually_exclusive_group()
        action.add_argument("--check", action="store_true", help="ratchet check")
        action.add_argument(
            "--update",
            action="store_true",
            help="adopt the first baseline, then shrink it; never adds a violation",
        )
        action.add_argument("--json", action="store_true", help="emit JSON report")
        action.add_argument(
            "--suggest",
            action="store_true",
            help="print a starter ring table and the reasons for each module; "
            "writes nothing and is never applied automatically",
        )
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
            "--allow-config-change",
            action="store_true",
            help="accept a layer policy that widens imports (recorded by --update)",
        )
        parser.add_argument(
            "--tripwire",
            action="store_true",
            help="post-merge push:[main] mode: an absent base baseline is the "
            "one-time adoption merge and bootstrap-passes",
        )
        return parser


class Cli:
    """Scan the package and route the request to the gate or a report."""

    _opts: Options

    def __new__(cls, options: Options) -> Self:
        self = super().__new__(cls)
        self._opts = options
        return self

    def run(self) -> int:
        """Execute the requested operation and return its exit code."""
        if not SourceSet.path(self._opts.src).exists():
            return self._emit(Outcome.failed(f"Not found: {self._opts.src}"))
        if self._opts.suggest:
            return self._emit(self._suggest())
        git = EdgeGate.repo(self._opts.src)
        root = git.root
        if root is None or not SourceSet(self._opts.src).inside(root):
            msg = f"FAIL: {self._opts.src} is not inside a git repository"
            return self._emit(Outcome.failed(msg))
        try:
            outcome = self._dispatch(LayerScan(self._opts.src), git)
        except FAILURES as exc:
            outcome = Outcome.failed(f"FAIL: {exc}")
        return self._emit(outcome)

    def _suggest(self) -> Outcome:
        """Print the suggestion; it reads no git state, so no repository is needed."""
        try:
            return Suggestion(self._opts.src).outcome()
        except FAILURES as exc:
            return Outcome.failed(f"FAIL: {exc}")

    def _dispatch(self, scan: LayerScan, git: GitRepo) -> Outcome:
        opts = self._opts
        if opts.check or opts.update:
            lines, code = self._gate(EdgeGate(opts.src, scan, git))
            return Outcome(code, tuple(lines))
        report = LayersReport(scan)
        if opts.json:
            return Outcome.passed(report.to_json())
        return Outcome.passed(*report.render())

    def _gate(self, gate: EdgeGate) -> tuple[list[str], int]:
        opts = self._opts
        if opts.check:
            return gate.check(
                base_ref=opts.base_ref,
                require_base=opts.require_base,
                tripwire=opts.tripwire,
                allow_config_change=opts.allow_config_change,
            )
        return gate.update(
            allow_ci_write=opts.allow_ci_write,
            source=opts.source,
            config_change=opts.allow_config_change,
        )

    @staticmethod
    def _emit(outcome: Outcome) -> int:
        sys.stdout.writelines(line + "\n" for line in outcome.lines)
        return outcome.exit_code


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the layers ratchet CLI, returning an exit code."""
    try:
        return Cli(Options.parse(argv)).run()
    except StateError as exc:  # raised while locating the repository root
        sys.stdout.write(f"FAIL: {exc}\n")
        return 1
