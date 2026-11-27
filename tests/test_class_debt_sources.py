"""Structural rules of the class-debt unit (A4, PL-1722): source selection."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "oo_ratchet"


def _classes() -> set[str]:
    names: set[str] = set()
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names.update(n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
    return names


HOLLOW = ["ImportArgs", "SourceSet", "SourceOptions", "NamespaceRescan"]
OPTION_CLASSES = ["OoOptions", "CouplingOptions", "SuppressionOptions", "LayersOptions"]
COMMAND_CLASSES = [
    "OoCommand",
    "CouplingCommand",
    "SuppressionCommand",
    "LayersCommand",
]


@pytest.mark.parametrize("name", [*HOLLOW, *OPTION_CLASSES, *COMMAND_CLASSES])
def test_hollow_class_is_gone(name: str) -> None:
    assert name not in _classes()


@pytest.mark.parametrize(
    "name", ["SourceSelection", "SourceHistory", "SourceArchive", "GateOptions"]
)
def test_class_is_defined_once(name: str) -> None:
    defs = [
        path
        for path in PACKAGE.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ClassDef) and node.name == name
    ]
    assert len(defs) == 1, defs


def test_source_selection_keeps_only_selection_methods() -> None:
    from oo_ratchet.source_set import SourceSelection

    for moved in ("at_base", "remap_metrics", "shadow", "report_paths", "rescan"):
        assert not hasattr(SourceSelection, moved), moved
    methods = [m for m in vars(SourceSelection) if not m.startswith("__")]
    assert len(methods) <= 24, methods
