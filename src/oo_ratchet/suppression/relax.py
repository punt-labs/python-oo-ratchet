"""Suppression relax ledger: audited, justified ceilings for legitimate growth.

The suppression ratchet is a hard, unconditional, regression-only gate with
no ``--allow-no-improvement`` escape valve (unlike the OO ratchet) -- every
net-new suppression must be removed or explicitly waived here, with a
reason, or the gate blocks forever.

A ledger entry records a *ceiling*: the total suppression count ``file`` is
allowed to carry, not a delta subtracted from whatever rise shows up next.
A ceiling only waives the change that adds it. Once the entry merges, the
comparison base's own ledger carries the identical entry and it is retired:
it covers nothing in any later comparison, so a cleanup that lowers the
file's count is a real floor and suppressions cannot grow back up to the old
ceiling. A fresh rise needs a fresh ``--relax``, which rewrites the entry.
A rise beyond the ceiling is never covered, merged or not.
"""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import ClassVar, NamedTuple, Self

logger = logging.getLogger(__name__)


class SuppressionRelaxError(Exception):
    """The in-tree ``.suppression-relax.json`` ledger could not be parsed."""


class RelaxEntry(NamedTuple):
    """One audited, justified suppression-count ceiling for a file."""

    file: str
    ceiling: int
    justify: str
    added_at: str


class SuppressionRelax:
    """A git-tracked ledger of justified, per-file suppression-count ceilings."""

    RELAX_FILE: ClassVar[str] = ".suppression-relax.json"

    _path: Path
    _entries: dict[str, RelaxEntry]
    _retired: set[str]

    def __new__(cls, root: Path) -> Self:
        self = super().__new__(cls)
        self._path = root / cls.RELAX_FILE
        self._entries = self._load()
        self._retired = set()
        return self

    @property
    def path(self) -> Path:
        """Return the ledger file's path."""
        return self._path

    def ceiling(self, fpath: str) -> int | None:
        """Return the recorded ceiling for ``fpath``, or ``None`` if unwaived."""
        entry = self._entries.get(fpath)
        if entry is None or fpath in self._retired:
            return None
        return entry.ceiling

    def retire_merged(self, base_text: str | None) -> None:
        """Retire every entry the base commit's ledger already carries unchanged."""
        merged = self._parse(base_text) if base_text is not None else {}
        self._retired = {f for f, e in merged.items() if self._entries.get(f) == e}

    def add(self, *, file: str, ceiling: int, justify: str) -> None:
        """Record a ceiling for ``file``, overwriting any prior entry."""
        self._entries[file] = RelaxEntry(file, ceiling, justify, self._now())
        self._retired.discard(file)
        self._save()

    def _load(self) -> dict[str, RelaxEntry]:
        if not self._path.exists():
            return {}
        try:
            text = self._path.read_text()
        except (OSError, UnicodeDecodeError) as exc:
            msg = f"unreadable suppression relax ledger {self._path}: {exc}"
            raise SuppressionRelaxError(msg) from exc
        return self._parse(text)

    def _parse(self, text: str) -> dict[str, RelaxEntry]:
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            msg = f"unreadable suppression relax ledger {self._path}: {exc}"
            raise SuppressionRelaxError(msg) from exc
        if not isinstance(raw, list):
            msg = f"non-list suppression relax ledger {self._path}"
            raise SuppressionRelaxError(msg)
        entries: dict[str, RelaxEntry] = {}
        for item in raw:
            entry = self._parse_entry(item)
            entries[entry.file] = entry
        return entries

    def _parse_entry(self, item: object) -> RelaxEntry:
        if not isinstance(item, dict):
            msg = f"non-dict entry in suppression relax ledger {self._path}"
            raise SuppressionRelaxError(msg)
        try:
            file = str(item["file"])
            raw_ceiling = item["ceiling"]
            # bool is an int subclass and JSON has no separate integer type
            # for a float like 2.9 -- silently coercing either would make
            # this "audited" ledger hold an inexact or fabricated ceiling
            # instead of raising on the malformed input.
            if isinstance(raw_ceiling, bool) or not isinstance(raw_ceiling, int):
                msg = f"non-integer ceiling for {file!r} in {self._path}"
                raise SuppressionRelaxError(msg)
            ceiling = raw_ceiling
            justify = str(item["justify"])
            added_at = str(item["added_at"])
        except (KeyError, TypeError, ValueError) as exc:
            msg = f"malformed entry in suppression relax ledger {self._path}: {exc}"
            raise SuppressionRelaxError(msg) from exc
        if ceiling <= 0:
            msg = f"non-positive ceiling for {file!r} in {self._path}"
            raise SuppressionRelaxError(msg)
        return RelaxEntry(file, ceiling, justify, added_at)

    def _save(self) -> None:
        data = [
            {
                "file": e.file,
                "ceiling": e.ceiling,
                "justify": e.justify,
                "added_at": e.added_at,
            }
            for e in sorted(self._entries.values(), key=lambda e: e.file)
        ]
        self._path.write_text(json.dumps(data, indent=2) + "\n")
        logger.info("Wrote suppression relaxations %s: %d files", self._path, len(data))

    @staticmethod
    def _now() -> str:
        return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
