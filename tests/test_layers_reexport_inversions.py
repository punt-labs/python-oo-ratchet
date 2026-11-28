"""The package ``__init__`` files import nothing, and no re-export inversion remains."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from oo_ratchet.core.domain.findings import Rules
from oo_ratchet.design.scan import DesignScanner

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "oo_ratchet"
GATE_PACKAGES = ("coupling", "layers", "oo", "suppression")


class TestGatePackageInits:
    """A gate package's ``__init__`` re-exports nothing from an outer ring."""

    @pytest.mark.parametrize("name", GATE_PACKAGES)
    def test_init_imports_only_future_annotations(self, name: str) -> None:
        tree = ast.parse((PACKAGE / name / "__init__.py").read_text())
        imports = [
            n for n in ast.walk(tree) if isinstance(n, ast.Import | ast.ImportFrom)
        ]
        modules = [n.module for n in imports if isinstance(n, ast.ImportFrom)]
        assert (len(imports), modules) == (1, ["__future__"])


class TestOwnLayerImports:
    """The design scan of this package reports none of the inversions fixed here."""

    def test_no_layer_import_from_inits_scanner_or_strict(self) -> None:
        report = DesignScanner(PACKAGE, ROOT / "pyproject.toml").report
        findings = json.loads(report.to_json())["findings"]
        watched = (
            *(f"{name}/__init__.py" for name in GATE_PACKAGES),
            "layers/strict.py",
        )
        hits = [
            f"{f['path']}:{f['line']} {f['symbol']}"
            for f in findings
            if f["rule"] == Rules.LAYER_IMPORT and f["path"].endswith(watched)
        ]
        assert hits == []

    def test_design_scanner_shim_is_gone(self) -> None:
        assert not (PACKAGE / "design" / "scanner.py").exists()
