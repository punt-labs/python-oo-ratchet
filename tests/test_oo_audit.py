"""Unit tests for the audit log and its structural waiver scoping."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oo_ratchet.core.adapters.formats import AuditFormat
from oo_ratchet.core.adapters.jsonstore import AuditFile
from oo_ratchet.core.domain.errors import StateError
from oo_ratchet.core.domain.records import AuditRecord

FILENAME = ".oo-audit.jsonl"


def _relax(audit: AuditFile, path: str, metric: str) -> None:
    audit.append(
        AuditRecord(
            verdict="relaxed",
            deltas={path: {metric: [1.0, 3.0]}},
            files_scored=1,
            files_regressed=1,
            source="vox-x #1",
            commit="abc123",
            reason="accepted",
        )
    )


def _waivable(audit: AuditFile, base: str | None) -> frozenset[tuple[str, str]]:
    base_records = None if base is None else AuditFormat.decode(base)
    waivers = AuditRecord.waivers_since(audit.records(), base_records)
    return frozenset((w.path, w.metric) for w in waivers)


class TestRelaxationsSince:
    """Waiver scoping compares audit entries structurally, not by raw text."""

    def test_reformatted_base_line_still_matches(self, tmp_path: Path) -> None:
        audit = AuditFile(tmp_path / FILENAME)
        _relax(audit, "sub/w.py", "max_complexity")
        # The base log holds the SAME entry but reformatted: keys sorted, spaces
        # after separators -- a different raw string, same semantics.
        in_tree = (tmp_path / FILENAME).read_text().splitlines()[0]
        reformatted = json.dumps(
            json.loads(in_tree), sort_keys=True, separators=(", ", ": ")
        )
        assert reformatted != in_tree  # genuinely different bytes
        assert _waivable(audit, reformatted) == frozenset()

    def test_absent_base_leaves_relaxation_waivable(self, tmp_path: Path) -> None:
        audit = AuditFile(tmp_path / FILENAME)
        _relax(audit, "sub/w.py", "max_complexity")
        assert _waivable(audit, None) == {("sub/w.py", "max_complexity")}

    def test_different_base_entry_leaves_relaxation_waivable(
        self, tmp_path: Path
    ) -> None:
        audit = AuditFile(tmp_path / FILENAME)
        _relax(audit, "sub/w.py", "max_complexity")
        other = json.dumps({"verdict": "relaxed", "deltas": {"sub/other.py": {}}})
        assert _waivable(audit, other) == {("sub/w.py", "max_complexity")}


class TestMalformedAudit:
    """A malformed audit line is a controlled StateError, not a traceback."""

    def test_bad_working_tree_line_raises_state_error(self, tmp_path: Path) -> None:
        (tmp_path / FILENAME).write_text("<<<<<<< conflict marker\n")
        with pytest.raises(StateError):
            AuditFile(tmp_path / FILENAME).records()

    def test_bad_base_line_raises_state_error(self) -> None:
        with pytest.raises(StateError):
            AuditFormat.decode("{ not json")
