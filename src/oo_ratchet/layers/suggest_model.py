"""The plain values a ring suggestion passes between its steps."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModuleFacts:
    """The evidence for one module: sorted, so every report is reproducible.

    ``forced`` is why the module cannot be placed at all, when it cannot.
    ``marker`` is the string a module-level ``__ring__`` constant holds, and
    ``marker_problem`` says why a ``__ring__`` could not be used.
    """

    name: str
    io: tuple[str, ...]
    entry: tuple[str, ...]
    imports: tuple[str, ...]
    forced: str | None = None
    root: bool = False
    marker: str | None = None
    marker_problem: str | None = None


@dataclass(frozen=True, slots=True)
class Verdict:
    """A module's suggested ring and why.

    ``ring`` is ``None`` for a module with no ring. ``conflict`` then says the
    module's intent disagrees with its import evidence, as opposed to there
    being no intent at all. ``intended`` says the ring came from a declaration
    or a package name, not from entry evidence.
    """

    ring: str | None
    why: str
    conflict: bool = False
    intended: bool = False
