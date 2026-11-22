"""The append-only audit log of layers baseline updates."""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Self

from oo_ratchet.design.layer_edges import Edge

logger = logging.getLogger(__name__)


class LayersAudit:
    """Append ``.oo-layers-audit.jsonl`` -- the layers ratchet's trail."""

    _path: Path

    FILENAME: str = ".oo-layers-audit.jsonl"

    def __new__(cls, root: Path) -> Self:
        self = super().__new__(cls)
        self._path = root / cls.FILENAME
        return self

    @property
    def path(self) -> Path:
        """Return the on-disk audit log path."""
        return self._path

    def append(
        self,
        *,
        verdict: str,
        modules: int,
        violations: int,
        added: frozenset[Edge],
        removed: frozenset[Edge],
        commit: str | None,
        source: str | None,
        config_change: bool = False,
        retired: frozenset[Edge] = frozenset(),
    ) -> None:
        """Append one entry: ``adopt`` writes a first baseline, ``pass`` shrinks it."""
        entry: dict[str, object] = {
            "ts": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "commit": commit,
            "source": source,
            "modules_scanned": modules,
            "violations": violations,
            "verdict": verdict,
            "added": sorted(str(e) for e in added),
            "removed": sorted(str(e) for e in removed),
        }
        if config_change:
            entry["config_change"] = True
        if retired:
            entry["retired"] = sorted(str(e) for e in retired)
        with self._path.open("a") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
        logger.info("Appended %s entry to layers audit %s", verdict, self._path)
