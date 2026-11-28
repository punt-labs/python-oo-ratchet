"""Class and boundary rules that depend on a module's declared ring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oo_ratchet.core.domain.findings import Rules
from oo_ratchet.design.cli import main
from oo_ratchet.design.scan import DesignScanner

RINGS = """[tool.oo-ratchet.layers]
entry = ["pkg", "pkg.entry"]
adapters = ["pkg.adapters", "pkg.adapters.*"]
application = ["pkg.application"]
domain = ["pkg.domain", "pkg.domain.*"]
"""
DECLARED = """[tool.oo-ratchet.layers.kernel]
prefixes = ["domain", "adapters"]
imports = []

[tool.oo-ratchet.layers.edge]
prefixes = ["entry"]
imports = ["kernel"]
"""
STATELESS = "class Codec:\n    def decode(self, raw):\n        return raw\n"
BAG = (
    "class Codec:\n    def a(self):\n        return 1\n"
    "    def b(self):\n        return 2\n"
)
STORE = (
    "class Store:\n    def __init__(self):\n        self._d = {}\n"
    "    def get(self):\n        return self._d\n"
)
WIRE = "from .adapters.store import Store\n\n\ndef make():\n    return Store()\n"


def tree(tmp_path: Path, files: dict[str, str], config: str | None) -> Path:
    root = tmp_path / "pkg"
    root.mkdir()
    (root / "__init__.py").write_text("")
    for name, text in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        if target.parent != root:
            (target.parent / "__init__.py").touch()
    if config is not None:
        (tmp_path / "pyproject.toml").write_text(config)
    return root


def reported(root: Path, rule: str) -> set[str]:
    doc = json.loads(DesignScanner(root).report.to_json())
    return {
        Path(r["path"]).relative_to(root).as_posix()
        for r in doc["findings"]
        if r["rule"] == rule
    }


@pytest.mark.parametrize("source", [STATELESS, BAG], ids=["single", "bag"])
@pytest.mark.parametrize("ring", ["adapters", "entry"])
def test_stateless_class_in_boundary_ring_is_not_reported(
    tmp_path: Path, source: str, ring: str
) -> None:
    module = "adapters/codec.py" if ring == "adapters" else "entry.py"
    rule = Rules.STATELESS_SINGLE if source == STATELESS else Rules.STATELESS_BAG
    assert reported(tree(tmp_path, {module: source}, RINGS), rule) == set()


@pytest.mark.parametrize("module", ["domain/codec.py", "application.py"])
def test_stateless_class_in_inner_ring_is_still_reported(
    tmp_path: Path, module: str
) -> None:
    root = tree(tmp_path, {module: STATELESS}, RINGS)
    assert reported(root, Rules.STATELESS_SINGLE) == {module}


def test_stateless_class_without_rings_is_still_reported(tmp_path: Path) -> None:
    root = tree(tmp_path, {"adapters/codec.py": STATELESS}, None)
    assert reported(root, Rules.STATELESS_SINGLE) == {"adapters/codec.py"}


def test_stateless_class_with_declared_layers_is_still_reported(
    tmp_path: Path,
) -> None:
    root = tree(tmp_path, {"adapters/codec.py": STATELESS}, DECLARED)
    assert reported(root, Rules.STATELESS_SINGLE) == {"adapters/codec.py"}


def test_entry_may_import_a_concrete_adapter(tmp_path: Path) -> None:
    files = {"adapters/store.py": STORE, "entry.py": WIRE}
    assert reported(tree(tmp_path, files, RINGS), Rules.CONCRETE_IMPORT) == set()


def test_inner_ring_importing_a_concrete_class_is_still_reported(
    tmp_path: Path,
) -> None:
    files = {"adapters/store.py": STORE, "application.py": WIRE}
    root = tree(tmp_path, files, RINGS)
    assert reported(root, Rules.CONCRETE_IMPORT) == {"application.py"}


def test_concrete_import_without_rings_is_still_reported(tmp_path: Path) -> None:
    files = {"adapters/store.py": STORE, "entry.py": WIRE}
    root = tree(tmp_path, files, None)
    assert reported(root, Rules.CONCRETE_IMPORT) == {"entry.py"}


def test_unknown_ring_key_is_still_an_error(tmp_path: Path) -> None:
    root = tree(tmp_path, {}, RINGS + 'plugins = ["pkg.plugins"]\n')
    assert main([str(root)]) == 2
