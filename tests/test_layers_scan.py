"""The layers scan: which import edges are violations, via the design layer code."""

from __future__ import annotations

from pathlib import Path

import pytest

from oo_ratchet.design.layer_config import LayerConfigError
from oo_ratchet.design.layer_edges import Edge
from oo_ratchet.layers.scan import LayerScan, LayersScanError

DECLARED = """\
[tool.oo-ratchet.layers.kernel]
prefixes = ["kernel"]
imports = []

[tool.oo-ratchet.layers.service]
prefixes = ["service"]
imports = ["kernel"]

[tool.oo-ratchet.layers.cli]
prefixes = ["cli"]
imports = ["kernel", "service"]
"""
ORDERED = """\
[tool.oo-ratchet.layers]
entry = ["app.cli"]
domain = ["app.kernel", "app.kernel.*"]
"""


def _package(tmp_path: Path, files: dict[str, str], config: str = DECLARED) -> Path:
    """Write ``files`` under ``tmp_path/src/app`` and return that directory."""
    (tmp_path / "pyproject.toml").write_text(config)
    pkg = tmp_path / "src" / "app"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    for name, text in files.items():
        path = pkg / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return pkg


def _edges(tmp_path: Path, files: dict[str, str]) -> frozenset[Edge]:
    return LayerScan(_package(tmp_path, files)).edges


class TestViolations:
    """An edge is a violation when its source layer may not import its target."""

    def test_allowed_edge_is_not_a_violation(self, tmp_path: Path) -> None:
        pkg = _package(
            tmp_path, {"kernel.py": "", "service.py": "from app import kernel\n"}
        )
        assert LayerScan(pkg).violations == ()

    def test_edge_to_a_layer_not_allowed_is_a_violation(self, tmp_path: Path) -> None:
        pkg = _package(
            tmp_path, {"kernel.py": "import app.service\n", "service.py": ""}
        )
        (violation,) = LayerScan(pkg).violations
        assert violation.edge == Edge("app.kernel", "app.service")
        assert (violation.source_layer, violation.target_layer) == (
            "kernel",
            "service",
        )

    def test_edge_inside_one_layer_is_allowed(self, tmp_path: Path) -> None:
        pkg = _package(
            tmp_path,
            {
                "kernel/__init__.py": "",
                "kernel/a.py": "from app.kernel import b\n",
                "kernel/b.py": "",
            },
        )
        assert LayerScan(pkg).violations == ()

    def test_unassigned_module_is_exempt_both_ways(self, tmp_path: Path) -> None:
        pkg = _package(
            tmp_path,
            {
                "kernel.py": "import app.stray\n",
                "stray.py": "import app.kernel\nimport app.cli\n",
                "cli.py": "",
            },
        )
        scan = LayerScan(pkg)
        assert scan.violations == ()
        assert scan.unassigned == ("app.stray",)

    def test_ordered_form_still_gates(self, tmp_path: Path) -> None:
        pkg = _package(
            tmp_path,
            {"kernel.py": "import app.cli\n", "cli.py": "import app.kernel\n"},
            ORDERED,
        )
        (violation,) = LayerScan(pkg).violations
        assert violation.edge == Edge("app.kernel", "app.cli")
        assert (violation.source_layer, violation.target_layer) == ("domain", "entry")


class TestRelativeImports:
    """Relative imports resolve to the same names the config classifies."""

    def test_from_dotted_parent_import(self, tmp_path: Path) -> None:
        pkg = _package(
            tmp_path,
            {
                "kernel.py": "from .service.handler import x\n",
                "service/__init__.py": "",
                "service/handler.py": "",
            },
        )
        assert Edge("app.kernel", "app.service.handler") in LayerScan(pkg).edges

    def test_relative_import_of_a_sibling_layer(self, tmp_path: Path) -> None:
        pkg = _package(
            tmp_path,
            {
                "kernel/__init__.py": "",
                "kernel/low.py": "from ..service import api\n",
                "service/__init__.py": "",
                "service/api.py": "",
            },
        )
        targets = {v.edge.target for v in LayerScan(pkg).violations}
        assert "app.service.api" in targets

    def test_relative_inside_one_layer_is_allowed(self, tmp_path: Path) -> None:
        pkg = _package(
            tmp_path,
            {
                "service/__init__.py": "from . import util\n",
                "service/util.py": "from .. import kernel\n",
                "kernel.py": "",
            },
        )
        assert LayerScan(pkg).violations == ()


class TestImportSites:
    """Every import site counts, as in the design gate, type-only included."""

    def test_type_checking_import_counts(self, tmp_path: Path) -> None:
        text = (
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n    import app.service\n"
        )
        pkg = _package(tmp_path, {"kernel.py": text, "service.py": ""})
        assert Edge("app.kernel", "app.service") in LayerScan(pkg).edges

    def test_import_inside_a_function_counts(self, tmp_path: Path) -> None:
        text = "def lazy() -> None:\n    import app.service\n"
        pkg = _package(tmp_path, {"kernel.py": text, "service.py": ""})
        assert Edge("app.kernel", "app.service") in LayerScan(pkg).edges

    def test_external_imports_are_not_edges(self, tmp_path: Path) -> None:
        assert _edges(tmp_path, {"kernel.py": "import os\nimport requests\n"}) == set()


class TestScanErrors:
    """A scan that cannot see every module fails instead of passing quietly."""

    def test_unparseable_module_fails_the_scan(self, tmp_path: Path) -> None:
        pkg = _package(tmp_path, {"broken.py": "def (:\n"})
        with pytest.raises(LayersScanError, match=r"broken\.py"):
            LayerScan(pkg)

    def test_missing_table_is_an_error(self, tmp_path: Path) -> None:
        pkg = _package(tmp_path, {}, "[tool.other]\nx = 1\n")
        with pytest.raises(LayerConfigError, match=r"no \[tool"):
            LayerScan(pkg)
