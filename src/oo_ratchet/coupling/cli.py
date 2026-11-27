"""Command-line entry point: parse arguments and dispatch to the gate."""

from __future__ import annotations

from typing import Self

from oo_ratchet.core.adapters.metricgate import MetricFiles, MetricGate
from oo_ratchet.core.domain.errors import StateError
from oo_ratchet.gate_options import (
    Flag,
    GateCommand,
    GateOptions,
    GateSpec,
    Kind,
    Report,
)

from .config import CouplingConfig, CouplingConfigError
from .gateinput import GateInput
from .report import CouplingReport
from .scorer import CouplingScorer

_FILES = MetricFiles(".oo-coupling-baseline.json", ".oo-coupling-audit.jsonl")
_GUARDS = {
    "paths": "FAIL: --rebaseline-files requires at least one path",
    "reason": "FAIL: --rebaseline-files requires --reason <text>",
}


SPEC = GateSpec(
    prog="oo-ratchet coupling",
    description="module coupling/cohesion scorer and regression ratchet",
    # Exactly one action selects the operation; passing two is an argparse
    # error, not a silent first-wins pick.
    actions=(
        Flag("--check", Kind.SWITCH, "ratchet check"),
        Flag("--update", Kind.SWITCH, "scoped update"),
        Flag("--rebaseline", Kind.SWITCH, "reset baseline"),
        Flag("--threshold", Kind.SWITCH, "per-file table"),
        Flag("--relax", Kind.OPTIONAL, "relax one file's baseline", "FILE"),
        Flag(
            "--rebaseline-files",
            Kind.PATHS,
            "bounded scoped bless of named files, --reason required",
            "PATH[,PATH...]",
        ),
        Flag("--log", Kind.SWITCH, "show audit history"),
        Flag("--json", Kind.SWITCH, "emit JSON scores"),
    ),
    modifiers=(
        Flag("--justify", Kind.TEXT, "justification for --relax"),
        Flag(
            "--reason", Kind.TEXT, "justification for --rebaseline-files / --rebaseline"
        ),
        Flag("--base-ref", Kind.OPTIONAL, "comparison base commit", "REF"),
        Flag("--require-base", Kind.SWITCH, "fail if base unresolvable"),
        Flag("--allow-ci-write", Kind.SWITCH, "permit writes under CI"),
        Flag("--source", Kind.OPTIONAL, "audit source (PR/bead)", "REF"),
        Flag(
            "--tripwire",
            Kind.SWITCH,
            "post-merge push:[main] mode: an absent base baseline is the "
            "one-time adoption merge and bootstrap-passes",
        ),
    ),
)


class CouplingRun:
    """Score the target and route the request to the gate or a view."""

    _opts: GateOptions
    _gate: MetricGate

    def __new__(cls, options: GateOptions) -> Self:
        self = super().__new__(cls)
        self._opts = options
        self._gate = MetricGate(_FILES)
        return self

    def run(self) -> Report:
        """Execute the requested operation and return its report."""
        guard = self._rebaseline_files_guard()
        if guard is not None:
            return [guard], 1
        if not self._opts.anchor.exists():
            return [f"Not found: {self._opts.src}"], 1
        try:
            # Score inside the try: a read/decode failure (OSError,
            # UnicodeDecodeError) or a corrupt in-tree baseline must surface as a
            # clean non-zero, not a traceback.
            config = CouplingConfig.load(self._gate.root)
            scorer = CouplingScorer(self._opts.src, self._gate.root, config)
            gate_input = GateInput(config, scorer)
            self._gate.prepare(gate_input.policy, gate_input.measurement)
            lines, code = self._dispatch(scorer)
        except (StateError, CouplingConfigError, OSError, UnicodeDecodeError) as exc:
            lines, code = [f"FAIL: {exc}"], 1
        return lines, code

    def _rebaseline_files_guard(self) -> str | None:
        """Reject an empty path list or blank ``--reason`` before scoring."""
        if self._opts.rebaseline_files is None:
            return None
        if not self._opts.rebaseline_files:
            return _GUARDS["paths"]
        if not self._opts.reason.strip():
            return _GUARDS["reason"]
        return None

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
        return self._write() if self._writes else self._view(scorer)

    @property
    def _writes(self) -> bool:
        """Return whether the request writes the baseline or the ledger."""
        opts = self._opts
        return (
            opts.update
            or opts.rebaseline
            or opts.relax is not None
            or opts.rebaseline_files is not None
        )

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
    return GateCommand(SPEC, CouplingRun).main(argv)
