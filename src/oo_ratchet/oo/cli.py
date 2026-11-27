"""Command-line entry point: parse arguments and dispatch to the ratchet."""

from __future__ import annotations

from oo_ratchet.core.adapters.oogate import OoGate
from oo_ratchet.core.application.policy import GatePolicy
from oo_ratchet.gate_options import Flag, GateCommand, GateOptions, GateSpec, Kind

from .scorer import Scorer
from .thresholds import Thresholds

POLICY = GatePolicy.from_table(Thresholds.TABLE, Thresholds.CEILINGS)

SPEC = GateSpec(
    prog="oo-ratchet oo",
    description="OO quality scorer and baseline ratchet",
    # Exactly one action selects the operation; passing two is an argparse
    # error, not a silent first-wins pick. --log and --json are distinct views,
    # not modifiers: each selects the operation on its own.
    actions=(
        Flag("--check", Kind.SWITCH, "ratchet check"),
        Flag("--update", Kind.SWITCH, "scoped update"),
        Flag("--reconcile", Kind.SWITCH, "whole-tree"),
        Flag("--rebaseline", Kind.SWITCH, "reset baseline"),
        Flag("--threshold", Kind.SWITCH, "per-file table"),
        Flag("--audit-completeness", Kind.SWITCH, "whole-tree completeness"),
        Flag("--relax", Kind.OPTIONAL, "relax one file's baseline", "FILE"),
        Flag(
            "--rebaseline-files",
            Kind.PATHS,
            "DES-097: bounded scoped bless of named files, --reason required",
            "PATH[,PATH...]",
        ),
        Flag("--log", Kind.SWITCH, "show audit history"),
        Flag("--json", Kind.SWITCH, "emit JSON scores"),
    ),
    modifiers=(
        Flag("--justify", Kind.TEXT, "justification for --relax"),
        Flag("--reason", Kind.TEXT, "justification for --rebaseline-files"),
        Flag("--base-ref", Kind.OPTIONAL, "comparison base commit", "REF"),
        Flag("--require-base", Kind.SWITCH, "fail if base unresolvable"),
        Flag(
            "--tripwire",
            Kind.SWITCH,
            "post-merge push:[main] mode: an absent base baseline is the "
            "one-time adoption merge and bootstrap-passes",
        ),
        # Waive only the must-improve gate (mechanical version-bump PRs improve
        # no metric); regressions and baseline lock-in are still enforced.
        Flag(
            "--allow-no-improvement",
            Kind.SWITCH,
            "waive the must-improve gate; still reject regressions",
        ),
        Flag("--allow-ci-write", Kind.SWITCH, "permit writes under CI"),
        Flag("--source", Kind.OPTIONAL, "audit source (PR/bead)", "REF"),
    ),
)


def _gate(options: GateOptions) -> OoGate:
    return OoGate(options, Scorer, POLICY)


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the ratchet CLI, returning an exit code."""
    return GateCommand(SPEC, _gate).main(argv)
