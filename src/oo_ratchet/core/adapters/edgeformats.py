"""The on-disk JSON formats of the layers gate: baseline and audit log."""

from __future__ import annotations

import json
from collections import defaultdict

from oo_ratchet.core.domain.edges import EdgeBook, EdgeRecord
from oo_ratchet.core.domain.errors import StateError
from oo_ratchet.design.layer_edges import Edge


class EdgeFormat:
    """``{source: [target, ...]}``, sorted by source, two-space indented."""

    @staticmethod
    def decode(text: str, label: str) -> EdgeBook:
        """Parse baseline JSON read from ``label``, or raise ``StateError``."""
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError as exc:
            msg = f"unreadable layers baseline {label}: {exc}"
            raise StateError(msg) from exc
        if not isinstance(loaded, dict) or not all(
            isinstance(targets, list) and all(isinstance(t, str) for t in targets)
            for targets in loaded.values()
        ):
            msg = f"layers baseline {label} must map a module to a list of modules"
            raise StateError(msg)
        edges = (Edge(s, t) for s, targets in loaded.items() for t in targets)
        return EdgeBook(frozenset(edges))

    @staticmethod
    def encode(book: EdgeBook) -> str:
        """Return the file text for ``book``."""
        grouped: defaultdict[str, list[str]] = defaultdict(list)
        for edge in sorted(book.edges):
            grouped[edge.source].append(edge.target)
        return json.dumps(dict(grouped), indent=2) + "\n"


class EdgeAuditFormat:
    """One compact JSON object per line."""

    @staticmethod
    def encode(record: EdgeRecord, stamp: str) -> bytes:
        """Return the line for ``record``, stamped ``stamp``, newline-terminated."""
        entry: dict[str, object] = {
            "ts": stamp,
            "commit": record.commit,
            "source": record.source,
            "modules_scanned": record.modules,
            "violations": record.violations,
            "verdict": record.verdict,
            "added": sorted(str(e) for e in record.added),
            "removed": sorted(str(e) for e in record.removed),
        }
        if record.config_change:
            entry["config_change"] = True
        if record.retired:
            entry["retired"] = sorted(str(e) for e in record.retired)
        return (json.dumps(entry, separators=(",", ":")) + "\n").encode()
