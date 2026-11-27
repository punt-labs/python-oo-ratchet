"""The file and report adapters: formats, stores, config, report rendering."""

from __future__ import annotations

from pathlib import Path

import pytest

from oo_ratchet.core.adapters.formats import AuditFormat, BaselineFormat
from oo_ratchet.core.adapters.gatecli import GateCli
from oo_ratchet.core.adapters.jsonstore import AuditFile, JsonBaselineStore
from oo_ratchet.core.adapters.pyprojectconfig import PyprojectConfig
from oo_ratchet.core.adapters.sourcetree import SourceTree
from oo_ratchet.core.domain.errors import StateError
from oo_ratchet.core.domain.records import AuditRecord
from oo_ratchet.core.domain.scores import Measurement, Score
from oo_ratchet.core.domain.verdicts import (
    Failure,
    FileReview,
    MetricRow,
    Review,
    Verdict,
)


@pytest.mark.parametrize(
    "text",
    ["{", "[]", '{"a.py": "x"}', '{"a.py": {"m": true}}', '{"a.py": {"m": "1"}}'],
)
def test_baseline_format_fails_closed(text: str) -> None:
    with pytest.raises(StateError):
        BaselineFormat.decode(text, "t")


def test_baseline_format_round_trips_sorted() -> None:
    text = BaselineFormat.encode({"b.py": {"m": 1.0}, "a.py": {"m": 2.0}})
    assert text.index("a.py") < text.index("b.py")
    assert BaselineFormat.decode(text, "t") == {"a.py": {"m": 2.0}, "b.py": {"m": 1.0}}


def test_audit_format_round_trips_and_keeps_extras() -> None:
    record = AuditRecord(
        verdict="rebaseline-files",
        deltas={"a.py": {"m": [1.0, 2.0]}},
        files_scored=1,
        reason="why",
        source="s",
        commit="abc",
        extra={"improved": {}},
    )
    (back,) = AuditFormat.decode(AuditFormat.encode(record, "2026-01-01T00:00:00Z"))
    assert back.ts == "2026-01-01T00:00:00Z"
    assert (back.verdict, back.reason, back.extra) == (
        "rebaseline-files",
        "why",
        {"improved": {}},
    )
    assert back.waivers() == record.waivers()


def test_audit_format_names_the_bad_line() -> None:
    with pytest.raises(StateError, match="malformed audit entry"):
        AuditFormat.decode('{"verdict": "x"}\n<<<<<<< conflict\n')


def test_audit_record_key_ignores_key_order() -> None:
    a = AuditRecord("relaxed", deltas={"a.py": {"m": [1, 2], "n": [3, 4]}})
    b = AuditRecord("relaxed", deltas={"a.py": {"n": [3, 4], "m": [1, 2]}})
    assert a.key() == b.key()


def test_stores_persist_and_stamp(tmp_path: Path) -> None:
    store = JsonBaselineStore(tmp_path / "b.json")
    assert not store.exists()
    assert store.rows() == {}
    store.save({"a.py": {"m": 1.0}})
    assert store.rows() == {"a.py": {"m": 1.0}}
    audit = AuditFile(tmp_path / "a.jsonl")
    assert audit.records() == ()
    audit.append(AuditRecord("pass"))
    assert audit.records()[0].ts is not None


def test_store_rejects_a_corrupt_file(tmp_path: Path) -> None:
    (tmp_path / "b.json").write_text("{")
    with pytest.raises(StateError):
        JsonBaselineStore(tmp_path / "b.json").rows()


def test_pyproject_table(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text('[tool.oo-ratchet.layers]\nentry = ["x"]\n[tool]\nbad = 1\n')
    cfg = PyprojectConfig(path)
    assert cfg.table("tool", "oo-ratchet", "layers") == {"entry": ["x"]}
    assert cfg.table("tool", "ruff") == {}
    with pytest.raises(StateError):
        cfg.table("tool", "bad")
    assert PyprojectConfig(tmp_path / "none.toml").table("tool") == {}
    path.write_text("[")
    with pytest.raises(StateError):
        PyprojectConfig(path)


def test_source_tree_keys_and_existence(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("")
    scan = Measurement((Score("a.py", {"m": 1.0}),))
    tree = SourceTree(tmp_path, lambda: scan)
    assert tree.measure() is scan
    assert tree.exists("a.py")
    assert not tree.exists("b.py")
    assert tree.key("./a.py") == "a.py"
    assert tree.key(str(tmp_path / "a.py")) == "a.py"
    assert tree.key("/elsewhere/x.py") == "/elsewhere/x.py"


def test_gate_cli_text_and_json() -> None:
    row = MetricRow("a.py", "m", "1.000", "2.000", "+1.000", "REGRESSED")
    review = Review((FileReview("a.py", rows=(row,), regressed=("m",)),))
    verdict = Verdict(
        failures=(Failure("regression", ("a.py: m",)), Failure("stale-row", ("a.py",))),
        review=review,
    )
    cli = GateCli("make update-oo")
    text = cli.text(verdict)
    assert any("REGRESSED" in ln for ln in text)
    assert "FAIL: regression detected: a.py: m" in text
    assert "FAIL: baseline out of date -- run make update-oo: a.py" in text
    assert cli.exit_code(verdict) == 1
    assert '"kind": "regression"' in cli.json(verdict)
    assert cli.text(Verdict.ok("fine"))[-1] == "PASS: fine"
    assert cli.exit_code(Verdict.ok()) == 0


def test_ci_write_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    blocked = GateCli.write_blocked(allow_ci_write=False)
    assert blocked is not None
    assert not blocked.passed
    assert GateCli.write_blocked(allow_ci_write=True) is None
    monkeypatch.delenv("GITHUB_ACTIONS")
    assert GateCli.write_blocked(allow_ci_write=False) is None
