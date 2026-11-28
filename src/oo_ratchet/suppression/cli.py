"""Command-line entry point: parse arguments and dispatch to the ratchet."""

from __future__ import annotations

from typing import Self

from oo_ratchet.core.adapters.outcomelog import OutcomeLog
from oo_ratchet.core.adapters.tallygate import GateFiles, TallyGate
from oo_ratchet.core.domain.errors import StateError
from oo_ratchet.core.domain.tallies import Tally
from oo_ratchet.gate_options import (
    Flag,
    GateCommand,
    GateOptions,
    GateSpec,
    Kind,
    Report,
)

from .gateinput import Scanner
from .pyproject import PyprojectError
from .report import SuppressionReport

_FILES = GateFiles(
    ".suppression-baseline.json",
    ".suppression-audit.jsonl",
    ".suppression-relax.json",
)


SPEC = GateSpec(
    prog="oo-ratchet suppressions",
    description="count lint/type suppressions and enforce a ratchet",
    actions=(
        Flag("--check", Kind.SWITCH, "ratchet check"),
        Flag("--update", Kind.SWITCH, "update baseline"),
        Flag(
            "--rebaseline",
            Kind.SWITCH,
            "audited reset to current counts (may raise), --reason required",
        ),
        Flag("--threshold", Kind.SWITCH, "per-file table"),
        Flag("--json", Kind.SWITCH, "emit JSON counts"),
        Flag("--relax", Kind.OPTIONAL, "waive one file's rise", "FILE"),
    ),
    modifiers=(
        Flag("--justify", Kind.TEXT, "justification for --relax"),
        Flag("--reason", Kind.TEXT, "reason for --rebaseline"),
        Flag("--source", Kind.OPTIONAL, "PR/issue recorded in the audit entry", "REF"),
        Flag("--base-ref", Kind.OPTIONAL, "comparison base commit", "REF"),
        Flag("--require-base", Kind.SWITCH, "fail if base unresolvable"),
        Flag("--allow-ci-write", Kind.SWITCH, "permit writes under CI"),
        Flag(
            "--tripwire",
            Kind.SWITCH,
            "post-merge push:[main] mode: an absent base baseline is the "
            "one-time adoption merge and bootstrap-passes",
        ),
    ),
)


class SuppressionRun:
    """Scan the target and route the request to the ratchet or a view."""

    _opts: GateOptions
    _gate: TallyGate

    def __new__(cls, options: GateOptions) -> Self:
        self = super().__new__(cls)
        self._opts = options
        self._gate = TallyGate(
            _FILES, options.src, lambda target, root: Scanner(target, root).report.tally
        )
        return self

    @property
    def _writes(self) -> bool:
        """Return whether the request writes the baseline or the ledger."""
        opts = self._opts
        return any((opts.update, opts.rebaseline, opts.relax is not None))

    def run(self) -> Report:
        """Execute the requested operation and return its report."""
        if not self._opts.anchor.exists():
            return [f"not found: {self._opts.src}"], 1
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
            OutcomeLog.unreadable(exc)
            lines, code = [f"FAIL: {exc}"], 1
        return lines, code

    def _dispatch(self, report: SuppressionReport) -> Report:
        opts = self._opts
        tally = report.tally
        if opts.check:
            return self._gate.check(
                tally,
                base_ref=opts.base_ref,
                require_base=opts.require_base,
                tripwire=opts.tripwire,
            )
        return self._write(tally) if self._writes else self._view(report)

    def _view(self, report: SuppressionReport) -> Report:
        if self._opts.json:
            return [report.to_json()], 0
        lines = list(report.render())
        if self._opts.threshold:
            lines.extend(report.render_threshold())
        return lines, 0

    def _write(self, tally: Tally) -> Report:
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
        return self._relax(tally)

    def _relax(self, tally: Tally) -> Report:
        opts = self._opts
        return self._gate.relax(
            tally,
            base_ref=opts.base_ref,
            file=opts.relax or "",
            justify=opts.justify,
            allow_ci_write=opts.allow_ci_write,
        )


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the suppression ratchet CLI, returning a code."""
    return GateCommand(SPEC, SuppressionRun).main(argv)
