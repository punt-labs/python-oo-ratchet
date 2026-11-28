"""The suppression package keeps counting pure and reading in the adapters ring."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from oo_ratchet.__main__ import main as dispatch
from oo_ratchet.design.scan import DesignScanner

ROOT = Path(__file__).resolve().parent.parent


def _findings_for(*suffixes: str) -> list[dict[str, object]]:
    doc = json.loads(DesignScanner(ROOT / "src" / "oo_ratchet").report.to_json())
    return [
        f
        for f in doc["findings"]
        if str(f["path"]).endswith(suffixes)
        and f["rule"] in {"domain-io", "layer-import"}
    ]


class TestSuppressionRings:
    """The domain counting module has no IO and no outward import."""

    def test_domain_counting_module_exists(self) -> None:
        assert (ROOT / "src/oo_ratchet/suppression/census.py").is_file()

    def test_suppression_modules_have_no_ring_findings(self) -> None:
        found = _findings_for("suppression/census.py", "suppression/gateinput.py")
        assert found == []

    def test_old_mixed_scanner_module_is_gone(self) -> None:
        assert not (ROOT / "src/oo_ratchet/suppression/scanner.py").exists()


# Real git init: the gate anchors its project root at the repository root.
@pytest.mark.slow
class TestCharacterization:
    """The report over a fixture tree is the same before and after the split."""

    def _tree(self, tmp_path: Path) -> Path:
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "a.py").write_text("x = 1  # noqa\ny = 2  # type: ignore\n")
        (pkg / "b.py").write_text("# ruff: noqa\nz = 3  # pylint: disable=x\n")
        (pkg / "bad.py").write_text("def (:  # noqa\n")
        (pkg / "c.py").write_bytes(b"# -*- coding: latin-1 -*-\nx = '\xe9'  # noqa\n")
        (tmp_path / "pyproject.toml").write_text(
            '[tool.ruff.lint.per-file-ignores]\n"docs/*" = ["E1", "E2"]\n'
        )
        return pkg

    def _run(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        flag: str,
    ) -> str:
        pkg = self._tree(tmp_path)
        monkeypatch.chdir(tmp_path)
        assert dispatch(["suppressions", str(pkg), flag]) == 0
        return capsys.readouterr().out

    def test_json_output_is_pinned(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        out = json.loads(self._run(tmp_path, capsys, monkeypatch, "--json"))
        files = {Path(k).name: v for k, v in out["by_file"].items()}
        assert (out["total"], out["by_category"], files) == (
            8,
            {
                "noqa": 3,
                "type_ignore": 1,
                "pylint_disable": 1,
                "pyright_ignore": 0,
                "file_level": 1,
                "per_file_ignores": 2,
            },
            {
                "a.py": {"noqa": 1, "type_ignore": 1},
                "b.py": {"pylint_disable": 1, "file_level": 1},
                "bad.py": {"noqa": 1},
                "c.py": {"noqa": 1},
                "*": {"per_file_ignores": 2},
            },
        )

    def test_text_output_is_pinned(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        out = self._run(tmp_path, capsys, monkeypatch, "--threshold")
        assert "Total suppressions: 8" in out
        assert "per_file_ignores" in out
