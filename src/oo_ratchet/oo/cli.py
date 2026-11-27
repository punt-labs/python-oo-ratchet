"""Command-line entry point: parse arguments and dispatch to the ratchet."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import ClassVar, Self

from oo_ratchet.core.adapters.oogate import OoGate
from oo_ratchet.core.application.policy import GatePolicy
from oo_ratchet.core.domain.errors import StateError
from oo_ratchet.source_set import Source, SourceSet

from .scorer import Scorer
from .thresholds import Thresholds


@dataclass(frozen=True, slots=True)
class OoOptions:
    """Parsed command-line options for one ratchet invocation."""

    src: Source
    check: bool
    update: bool
    reconcile: bool
    rebaseline: bool
    log: bool
    json: bool
    threshold: bool
    audit_completeness: bool
    relax: str | None
    rebaseline_files: tuple[str, ...] | None
    justify: str
    reason: str
    base_ref: str | None
    require_base: bool
    allow_no_improvement: bool
    tripwire: bool
    allow_ci_write: bool
    source: str | None

    @classmethod
    def parse(cls, argv: list[str] | None = None) -> Self:
        """Build options from ``argv`` (defaults to ``sys.argv``)."""
        ns = SourceSet.parse(cls._build_parser(), argv)
        return cls(
            src=ns.src,
            check=bool(ns.check),
            update=bool(ns.update),
            reconcile=bool(ns.reconcile),
            rebaseline=bool(ns.rebaseline),
            log=bool(ns.log),
            json=bool(ns.json),
            threshold=bool(ns.threshold),
            audit_completeness=bool(ns.audit_completeness),
            relax=ns.relax,
            rebaseline_files=cls._split_paths(ns.rebaseline_files),
            justify=ns.justify or "",
            reason=ns.reason or "",
            base_ref=ns.base_ref,
            require_base=bool(ns.require_base),
            allow_no_improvement=bool(ns.allow_no_improvement),
            tripwire=bool(ns.tripwire),
            allow_ci_write=bool(ns.allow_ci_write),
            source=ns.source,
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
            prog="oo-ratchet oo", description="OO quality scorer and baseline ratchet"
        )
        SourceSet.add(parser)
        # Exactly one action selects the operation; passing two is an argparse
        # error, not a silent first-wins pick.
        action = parser.add_mutually_exclusive_group()
        action.add_argument("--check", action="store_true", help="ratchet check")
        action.add_argument("--update", action="store_true", help="scoped update")
        action.add_argument("--reconcile", action="store_true", help="whole-tree")
        action.add_argument("--rebaseline", action="store_true", help="reset baseline")
        action.add_argument("--threshold", action="store_true", help="per-file table")
        action.add_argument(
            "--audit-completeness", action="store_true", help="whole-tree completeness"
        )
        action.add_argument("--relax", metavar="FILE", help="relax one file's baseline")
        action.add_argument(
            "--rebaseline-files",
            metavar="PATH[,PATH...]",
            help="DES-097: bounded scoped bless of named files, --reason required",
        )
        # --log and --json are distinct views, not modifiers: each selects the
        # operation on its own, so they join the exclusive group rather than be
        # silently ignored when combined with another action.
        action.add_argument("--log", action="store_true", help="show audit history")
        action.add_argument("--json", action="store_true", help="emit JSON scores")
        parser.add_argument("--justify", default="", help="justification for --relax")
        parser.add_argument(
            "--reason", default="", help="justification for --rebaseline-files"
        )
        parser.add_argument("--base-ref", metavar="REF", help="comparison base commit")
        parser.add_argument(
            "--require-base", action="store_true", help="fail if base unresolvable"
        )
        parser.add_argument(
            "--tripwire",
            action="store_true",
            help="post-merge push:[main] mode: an absent base baseline is the "
            "one-time adoption merge and bootstrap-passes",
        )
        # Waive only the must-improve gate (mechanical version-bump PRs improve
        # no metric); regressions and baseline lock-in are still enforced.
        parser.add_argument(
            "--allow-no-improvement",
            action="store_true",
            help="waive the must-improve gate; still reject regressions",
        )
        parser.add_argument(
            "--allow-ci-write", action="store_true", help="permit writes under CI"
        )
        parser.add_argument("--source", metavar="REF", help="audit source (PR/bead)")
        return parser


class OoCommand:
    """Run one OO command line on the shared core and print its report."""

    POLICY: ClassVar[GatePolicy] = GatePolicy.from_table(
        Thresholds.TABLE, Thresholds.CEILINGS
    )

    _opts: OoOptions

    def __new__(cls, options: OoOptions) -> Self:
        self = super().__new__(cls)
        self._opts = options
        return self

    def run(self) -> int:
        """Execute the requested operation and return its exit code."""
        try:
            lines, code = OoGate(self._opts, Scorer, self.POLICY).run()
        except StateError as exc:  # raised while locating the repository root
            lines, code = [f"FAIL: {exc}"], 1
        sys.stdout.writelines(line + "\n" for line in lines)
        return code


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the ratchet CLI, returning an exit code."""
    return OoCommand(OoOptions.parse(argv)).run()
