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


@pytest.mark.parametrize("name", ["ImportArgs"])
def test_hollow_class_is_gone(name: str) -> None:
    assert name not in _classes()
