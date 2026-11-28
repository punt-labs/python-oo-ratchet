"""The one command line every ratchet gate parses, runs and prints."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, Self

from oo_ratchet.core.adapters.outcomelog import OutcomeLog
from oo_ratchet.core.domain.errors import StateError

from .source_set import Source, SourceSelection
from .sources import Sources


class Kind(Enum):
    """How a flag's raw value becomes an option field."""

    SWITCH = "switch"
    TEXT = "text"
    OPTIONAL = "optional"
    PATHS = "paths"


@dataclass(frozen=True, slots=True)
class Flag:
    """One command-line flag: its spelling, help and the field it fills."""

    name: str
    kind: Kind
    help: str
    metavar: str | None = None

    @property
    def dest(self) -> str:
        """Return the option field this flag fills."""
        return self.name.removeprefix("--").replace("-", "_")

    def arguments(self) -> dict[str, Any]:
        """Return the keyword arguments argparse registers this flag with."""
        if self.kind is Kind.SWITCH:
            return {"action": "store_true", "help": self.help}
        if self.kind is Kind.TEXT:
            return {"default": "", "help": self.help}
        return {"metavar": self.metavar, "help": self.help}

    def read(self, ns: argparse.Namespace) -> Any:
        """Return this flag's field value from a parsed namespace."""
        raw = getattr(ns, self.dest)
        if self.kind is Kind.SWITCH:
            return bool(raw)
        if self.kind is Kind.TEXT:
            return raw or ""
        if self.kind is Kind.PATHS and raw is not None:
            return tuple(p.strip() for p in raw.split(",") if p.strip())
        return raw


@dataclass(frozen=True, slots=True)
class Needs:
    """A modifier that is an error unless one of the named actions is chosen."""

    fields: tuple[str, ...]
    unless: tuple[str, ...]
    message: str

    def violated(self, ns: argparse.Namespace) -> bool:
        """Return whether a modifier is set while no required action is."""
        return self._any(ns, self.fields) and not self._any(ns, self.unless)

    @staticmethod
    def _any(ns: argparse.Namespace, fields: tuple[str, ...]) -> bool:
        return any(getattr(ns, f) not in (None, False) for f in fields)


@dataclass(frozen=True, slots=True)
class GateSpec:
    """One gate's command line: its name, actions, modifiers and constraints."""

    prog: str
    description: str
    actions: tuple[Flag, ...]
    modifiers: tuple[Flag, ...]
    needs: tuple[Needs, ...] = ()

    def parser(self) -> argparse.ArgumentParser:
        """Build the gate's parser; the actions are mutually exclusive."""
        parser = argparse.ArgumentParser(prog=self.prog, description=self.description)
        GateOptions.add_source(parser)
        group = parser.add_mutually_exclusive_group()
        for flag in self.actions:
            group.add_argument(flag.name, **flag.arguments())
        for flag in self.modifiers:
            parser.add_argument(flag.name, **flag.arguments())
        return parser


@dataclass(frozen=True, slots=True)
class GateOptions:
    """Parsed command-line options for one gate invocation.

    A flag the gate does not offer keeps its default.
    """

    src: Source
    check: bool = False
    update: bool = False
    reconcile: bool = False
    rebaseline: bool = False
    log: bool = False
    json: bool = False
    threshold: bool = False
    audit_completeness: bool = False
    suggest: bool = False
    relax: str | None = None
    rebaseline_files: tuple[str, ...] | None = None
    justify: str = ""
    reason: str = ""
    base_ref: str | None = None
    require_base: bool = False
    allow_no_improvement: bool = False
    tripwire: bool = False
    allow_ci_write: bool = False
    allow_config_change: bool = False
    source: str | None = None

    @property
    def anchor(self) -> Path:
        """Return the physical path of the selected source."""
        return SourceSelection.path(self.src)

    @classmethod
    def parse(cls, spec: GateSpec, argv: list[str] | None = None) -> Self:
        """Build options from ``argv`` (defaults to ``sys.argv``)."""
        parser = spec.parser()
        ns = cls.namespace(parser, argv)
        for rule in spec.needs:
            if rule.violated(ns):
                parser.error(rule.message)
        fields: dict[str, Any] = {
            f.dest: f.read(ns) for f in (*spec.actions, *spec.modifiers)
        }
        return replace(cls(src=ns.src), **fields)

    @staticmethod
    def add_source(parser: argparse.ArgumentParser) -> None:
        """Add the source arguments shared by every gate."""
        parser.add_argument(
            "src", nargs="*", help="package directory or namespace portions"
        )
        parser.add_argument(
            "--namespace", help="join roots of this top-level namespace"
        )

    @staticmethod
    def namespace(
        parser: argparse.ArgumentParser, argv: list[str] | None
    ) -> argparse.Namespace:
        """Parse ``argv``; ``src`` is a legacy Path or a validated selection."""
        ns = parser.parse_args(argv)
        try:
            ns.src = Sources.select(ns.src, ns.namespace)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        if isinstance(ns.src, Sources):
            ns.src = SourceSelection(ns.src)
        return ns


type Report = tuple[list[str], int]


class Gate(Protocol):
    """What one gate does with its parsed options: report lines and an exit code."""

    def run(self) -> Report:
        """Execute the requested operation."""
        ...


class GateCommand:
    """Parse one gate's command line, run the gate and print its report.

    Locating the repository root can fail while a gate is built; that is a
    failing report, never a traceback.
    """

    _spec: GateSpec
    _build: Callable[[GateOptions], Gate]

    def __new__(cls, spec: GateSpec, build: Callable[[GateOptions], Gate]) -> Self:
        self = super().__new__(cls)
        self._spec = spec
        self._build = build
        return self

    def main(self, argv: list[str] | None = None) -> int:
        """Parse ``argv``, run the gate and return its exit code."""
        options = GateOptions.parse(self._spec, argv)
        try:
            lines, code = self._build(options).run()
        except StateError as exc:
            OutcomeLog.unreadable(exc)
            lines, code = [f"FAIL: {exc}"], 1
        sys.stdout.writelines(line + "\n" for line in lines)
        return code
