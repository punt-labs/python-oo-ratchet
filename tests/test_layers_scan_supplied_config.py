"""A layer config passed to LayerScan is not read from a nearby pyproject."""

from __future__ import annotations

from typing import TYPE_CHECKING

from oo_ratchet.core.domain.layer_table import LayerTable
from oo_ratchet.layers.scan import LayerScan

if TYPE_CHECKING:
    from pathlib import Path

LAYERS = '[tool.oo-ratchet.layers]\nentry = ["app.cli"]\ndomain = ["app.domain"]\n'


def test_supplied_config_ignores_a_malformed_pyproject(tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "app"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "domain.py").write_text("X = 1\n")
    (pkg / "cli.py").write_text("")
    (tmp_path / "pyproject.toml").write_text("this is [not toml\n")
    config = LayerTable.from_text(LAYERS, "t").config()
    assert config is not None
    scan = LayerScan(pkg, config)
    assert scan.config_path == tmp_path / "pyproject.toml"
