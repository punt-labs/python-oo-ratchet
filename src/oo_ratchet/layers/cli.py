"""Command-line entry point: parse arguments and dispatch to the ratchet."""

from __future__ import annotations

from typing import Self

from oo_ratchet.core.adapters.edgegate import EdgeGate
from oo_ratchet.core.adapters.gitrepo import GitRepo
from oo_ratchet.core.domain.exits import Outcome
from oo_ratchet.gate_options import (
    Flag,
    GateCommand,
    GateOptions,
    GateSpec,
    Kind,
    Needs,
    Report,
)
from oo_ratchet.source_set import SourceSelection

from .failures import FAILURES
from .report import LayersReport
from .scan import LayerScan
from .suggest import Suggestion

SPEC = GateSpec(
    prog="oo-ratchet layers",
    description="package layer contract: imports only point down the layers",
    actions=(
        Flag("--check", Kind.SWITCH, "ratchet check"),
        Flag(
            "--update",
            Kind.SWITCH,
            "adopt the first baseline, then shrink it; never adds a violation",
        ),
        Flag("--json", Kind.SWITCH, "emit JSON report"),
        Flag(
            "--suggest",
            Kind.SWITCH,
            "print a starter ring table and the reasons for each module; "
            "writes nothing and is never applied automatically",
        ),
    ),
    modifiers=(
        Flag("--base-ref", Kind.OPTIONAL, "comparison base commit (--check)", "REF"),
        Flag("--require-base", Kind.SWITCH, "fail if base unresolvable"),
        Flag("--allow-ci-write", Kind.SWITCH, "permit writes under CI"),
        Flag("--source", Kind.OPTIONAL, "audit source (PR/bead)", "REF"),
        Flag(
            "--allow-config-change",
            Kind.SWITCH,
            "accept a layer policy that widens imports (recorded by --update)",
        ),
        Flag(
            "--tripwire",
            Kind.SWITCH,
            "post-merge push:[main] mode: an absent base baseline is the "
            "one-time adoption merge and bootstrap-passes",
        ),
    ),
    needs=(
        Needs(
            ("base_ref", "require_base", "tripwire"),
            ("check",),
            "--base-ref, --require-base and --tripwire need --check",
        ),
        Needs(
            ("allow_config_change",),
            ("check", "update"),
            "--allow-config-change needs --check or --update",
        ),
    ),
)


class LayersRun:
    """Scan the package and route the request to the gate or a report."""

    _opts: GateOptions

    def __new__(cls, options: GateOptions) -> Self:
        self = super().__new__(cls)
        self._opts = options
        return self

    def run(self) -> Report:
        """Execute the requested operation and return its report."""
        if not self._opts.anchor.exists():
            return [f"Not found: {self._opts.src}"], 1
        outcome = self._suggest() if self._opts.suggest else self._checked()
        return list(outcome.lines), outcome.exit_code

    def _checked(self) -> Outcome:
        git = EdgeGate.repo(self._opts.src)
        if not self._inside(git):
            return Outcome.failed(
                f"FAIL: {self._opts.src} is not inside a git repository"
            )
        try:
            return self._dispatch(LayerScan(self._opts.src), git)
        except FAILURES as exc:
            return Outcome.failed(f"FAIL: {exc}")

    def _inside(self, git: GitRepo) -> bool:
        root = git.root
        return root is not None and SourceSelection(self._opts.src).inside(root)

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


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the layers ratchet CLI, returning an exit code."""
    return GateCommand(SPEC, LayersRun).main(argv)
