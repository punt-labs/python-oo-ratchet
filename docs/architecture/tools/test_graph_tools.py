"""Tests for graph_tools. Run: uv run pytest docs/architecture/tools/test_graph_tools.py"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

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
