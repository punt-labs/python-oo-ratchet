"""The OO scoring split: pure scoring in the domain, file reading in an adapter."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import TYPE_CHECKING

from oo_ratchet.__main__ import main as dispatch
from oo_ratchet.oo.tree import Scorer

if TYPE_CHECKING:
    import pytest

ROOT = Path(__file__).resolve().parent.parent
OO = ROOT / "src" / "oo_ratchet" / "oo"

GOOD = '''from __future__ import annotations


class Widget:
    """A widget."""

    _n: int

    def __new__(cls, n: int) -> "Widget":
        self = super().__new__(cls)
        self._n = n
        return self

    def label(self) -> str:
        return "pos"
'''
BAD = "import os\n\n\ndef f(a, b, c, d, e, g):\n    return os.sep\n"
BROKEN = "def oops(:\n    pass\n"

JSON_KEYS = ["per_file", "aggregate", "grades", "thresholds"]


def _fixture(tmp_path: Path) -> Path:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "good.py").write_text(GOOD)
    (pkg / "bad.py").write_text(BAD)
    (pkg / "broken.py").write_text(BROKEN)
    return pkg


class TestCharacterization:
    """Scoring output on a fixture tree; passes before and after the split."""

    def test_json_report_shape_and_values(self, tmp_path: Path) -> None:
        scorer = Scorer(_fixture(tmp_path), tmp_path)
        out = json.loads(scorer.to_json())
        assert list(out) == JSON_KEYS
        assert [r["file"] for r in out["per_file"]] == [
            "pkg/bad.py",
            "pkg/broken.py",
            "pkg/good.py",
        ]
        assert "error" in out["per_file"][1]
        assert out["grades"]["future_annotations"] == "FAIL"
        fails = [g for g in out["grades"].values() if g == "FAIL"]
        assert scorer.fail_count == len(fails)

    def test_rows_files_and_errors(self, tmp_path: Path) -> None:
        scorer = Scorer(_fixture(tmp_path), tmp_path)
        assert scorer.files == frozenset({"pkg/bad.py", "pkg/good.py"})
        assert scorer.parse_errors == frozenset({"pkg/broken.py"})
        assert set(scorer.rows) == scorer.files

    def test_rendering(self, tmp_path: Path) -> None:
        scorer = Scorer(_fixture(tmp_path), tmp_path)
        table = scorer.render_table()
        assert table[1] == "-" * 56
        assert any(line.startswith("future_annotations") for line in table)
        per_file = scorer.render_per_file()
        assert per_file[0] == "\n--- Per-file breakdown ---"
        assert "\n  pkg/good.py" in per_file

    def test_cli_exit_code_and_table(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _fixture(tmp_path)
        monkeypatch.chdir(tmp_path)
        code = dispatch(["oo", "pkg"])
        out = capsys.readouterr().out
        assert code == 1
        assert "Metric" in out


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    return names


class TestScoringIsDomain:
    """The pure scoring module takes data; the adapter reads files."""

    def test_scoring_module_imports_no_io_and_no_outer_ring(self) -> None:
        names = _imports(OO / "scoring.py")
        assert not names & {"json", "pathlib", "io", "os"}, names
        assert not any("source_set" in n or n.endswith("tree") for n in names), names

    def test_scoring_takes_result_dicts(self) -> None:
        from oo_ratchet.oo.scoring import Scoring

        scoring = Scoring(
            [{"file": "a.py", "avg_params": 2.0}, {"file": "b.py", "error": "x"}]
        )
        assert scoring.files == frozenset({"a.py"})
        assert scoring.parse_errors == frozenset({"b.py"})
        assert scoring.summary == {"avg_params": 2.0}

    def test_design_reports_no_finding_for_the_split_modules(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(ROOT)
        dispatch(["design", "src/oo_ratchet/"])
        lines = capsys.readouterr().out.splitlines()
        hits = [
            ln
            for ln in lines
            if ("oo/scor" in ln or "oo/tree" in ln) and "imports concrete" not in ln
        ]
        assert hits == []
        assert (OO / "scoring.py").exists()
