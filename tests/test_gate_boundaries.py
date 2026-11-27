"""Structural rules of the clean architecture plan (A3, PL-1721).

Each test reads the source tree: a class name belongs to one gate package or
the shared core, and the gates share one layer model rather than reach into
the design check for it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "oo_ratchet"
GATES = ("oo", "coupling", "suppression", "layers", "design")

# Names the plan says exactly one package may define. The list grows as each
# duplicate is removed.
SINGLE_OWNER = ("GitRepo", "GitError", "Diff", "Row")


def _classes(package: Path) -> set[str]:
    names: set[str] = set()
    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names.update(n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
    return names


@pytest.mark.parametrize("name", SINGLE_OWNER)
def test_class_name_is_defined_in_one_package(name: str) -> None:
    owners = [pkg for pkg in (*GATES, "core") if name in _classes(PACKAGE / pkg)]
    assert len(owners) <= 1, f"{name} is defined in {owners}"
