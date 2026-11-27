"""Tests for graph_tools. Run: uv run pytest docs/architecture/tools/test_graph_tools.py"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).parent
sys.path.insert(0, str(TOOLS))

from graph_tools import has_cycle, strongly_connected  # noqa: E402


def test_three_cycle_without_reciprocal_edges() -> None:
    graph = {"a": {"b"}, "b": {"c"}, "c": {"a"}}
    assert strongly_connected(graph) == [["a", "b", "c"]]
    assert has_cycle([("a", "b"), ("b", "c"), ("c", "a")])


def test_acyclic_chain() -> None:
    graph = {"entry": {"layers"}, "layers": {"design"}, "design": {"core"}}
    assert strongly_connected(graph) == []
    assert not has_cycle([("entry", "layers"), ("layers", "design"), ("design", "core")])


def test_two_separate_components_and_a_tail() -> None:
    graph = {"a": {"b"}, "b": {"a", "c"}, "c": {"d"}, "d": {"e"}, "e": {"c"}, "x": {"a"}}
    assert strongly_connected(graph) == [["a", "b"], ["c", "d", "e"]]


def test_self_import_is_a_cycle() -> None:
    assert strongly_connected({"a": {"a"}}) == [["a"]]
    assert has_cycle([("a", "a")])


def _package_graph(root: Path, *args: str) -> str:
    out = subprocess.run(
        [sys.executable, str(TOOLS / "package_graph.py"), str(root), *args],
        capture_output=True, text=True, check=True,
    )
    return out.stdout


def test_package_graph_finds_module_cycle_through_type_checking_import(
    tmp_path: Path,
) -> None:
    """The shape of source_archive/source_rescan: a runtime absolute import one way,
    a relative TYPE_CHECKING import back."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "archive.py").write_text(
        "from __future__ import annotations\n"
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from .rescan import Repo\n"
    )
    (pkg / "rescan.py").write_text(
        "from __future__ import annotations\n"
        "from pkg.archive import Archive\n"
    )
    (pkg / "leaf.py").write_text("from pkg.archive import Archive\n")
    out = _package_graph(pkg)
    assert "module cycles: 1 " in out
    assert "component: pkg.archive, pkg.rescan" in out


@pytest.mark.parametrize("back_edge", ["import pkg", "from pkg import NAME"])
def test_package_graph_counts_imports_of_the_root_package(
    tmp_path: Path, back_edge: str,
) -> None:
    """`import pkg` and `from pkg import name` reach the root __init__.py; a cycle
    through it is reported."""
    pkg = tmp_path / "pkg"
    (pkg / "a").mkdir(parents=True)
    (pkg / "__init__.py").write_text("from pkg.a.m import VALUE\nNAME = 1\n")
    (pkg / "a" / "__init__.py").write_text("")
    (pkg / "a" / "m.py").write_text(f"{back_edge}\nVALUE = 1\n")
    out = _package_graph(pkg)
    assert "module cycles: 1 " in out
    assert "component: pkg, pkg.a.m" in out
    assert "package cycles: 1" in out


def test_package_graph_cycle_across_subpackages_and_entry_split(tmp_path: Path) -> None:
    """A three-package loop with no reciprocal edge, and the entry/root split."""
    pkg = tmp_path / "pkg"
    for sub in ("a", "b", "c"):
        (pkg / sub).mkdir(parents=True)
        (pkg / sub / "__init__.py").write_text("")
    (pkg / "__init__.py").write_text("")
    (pkg / "a" / "m.py").write_text("from pkg.b import m\n")
    (pkg / "b" / "m.py").write_text("from pkg.c import m\n")
    (pkg / "c" / "m.py").write_text("from pkg.a import m\n")
    (pkg / "gates.py").write_text("from pkg.a import m\n")
    (pkg / "shared.py").write_text("")
    (pkg / "a" / "uses.py").write_text("from pkg import shared\n")
    out = _package_graph(pkg)
    assert "package cycles: 1" in out
    assert "component: a, b, c" in out
    assert "<entry>      -> a" in out
    assert "a            -> <root>" in out
