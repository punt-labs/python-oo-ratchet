"""The text of a suggestion: the header and the three lists, each line reasoned."""

from __future__ import annotations

from typing import Self

from .suggest_model import Verdict
from .suggest_text import SafeText

HEADER = (
    "# oo-ratchet layers --suggest {package}: a starting point, never applied.",
    "# Nothing was written. A wrong ring lets forbidden imports pass: review each",
    "# reason below, then copy the table into pyproject.toml yourself.",
    "# A ring comes from intent, never from a guess: a declaration (a module-level",
    '# __ring__ = "domain" string, or an existing fixed-form [tool.oo-ratchet.layers]',
    "# table), then a package name (domain, model, core suggest domain; adapters,",
    "# infra suggest adapters; [tool.oo-ratchet.suggest] replaces the names). The",
    "# one ring taken from evidence is entry: argparse, typer or a console script.",
    "# A module that reaches IO, directly or through imports, is never domain: that",
    "# is a CONFLICT, printed with the import path. A module with no intent stays",
    "# unclassified, with its evidence. The gate lets domain import only domain and",
    "# application import only application and domain, so a module importing a ring",
    "# it may not is a conflict too. A glob such as pkg.sub.* also claims any module",
    "# added later under that prefix. The package root goes in entry whatever it",
    "# imports, as vox, lux and z-spec place theirs; it is unclassified instead when",
    "# a non-entry module imports it or it has a relative import above the package.",
)


class RingLists:
    """Render verdicts as the header, then rings, conflicts and unclassified."""

    _verdicts: dict[str, Verdict]
    _package: str

    def __new__(cls, verdicts: dict[str, Verdict], package: str) -> Self:
        self = super().__new__(cls)
        self._verdicts = verdicts
        self._package = package
        return self

    @property
    def modules(self) -> tuple[str, ...]:
        """Return every module name, sorted."""
        return tuple(sorted(self._verdicts))

    def rings(self) -> dict[str, str]:
        """Return the ring of each module that has one."""
        return {n: v.ring for n, v in self._verdicts.items() if v.ring}

    def header(self) -> tuple[str, ...]:
        """Return the comment header, with the package name escaped."""
        safe = SafeText.comment(self._package)
        return tuple(line.format(package=safe) for line in HEADER)

    def notes(self) -> list[str]:
        ringed = [n for n in self.modules if self._verdicts[n].ring]
        clash = [n for n in self.modules if self._verdicts[n].conflict]
        free = [n for n in self.modules if n not in ringed and n not in clash]
        lines = ["", "# Ring from declaration, name or entry evidence:"]
        lines.extend(self._lines(ringed, None))
        lines.extend(("", "# Conflicts:"))
        lines.extend(self._lines(clash, "CONFLICT"))
        lines.extend(("", "# Unclassified:"))
        lines.extend(self._lines(free, "unclassified"))
        lines.extend(("", self._summary(ringed, clash, free)))
        return lines

    def _lines(self, names: list[str], label: str | None) -> list[str]:
        if not names:
            return ["#   none"]
        return [
            f"#   {SafeText.comment(n)}: {label or self._verdicts[n].ring} "
            f"({SafeText.comment(self._verdicts[n].why)})"
            for n in names
        ]

    def _summary(self, ringed: list[str], clash: list[str], free: list[str]) -> str:
        named = sum(1 for n in ringed if self._verdicts[n].intended)
        return (
            f"# Summary: {named} of {len(self.modules)} modules ring-assigned from "
            f"a declaration or name, {len(ringed) - named} from entry evidence, "
            f"{len(clash)} conflicts, {len(free)} unclassified."
        )
