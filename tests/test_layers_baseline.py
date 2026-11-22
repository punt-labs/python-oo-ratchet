"""Parsing the layers baseline: malformed or wrong-shaped JSON is refused."""

from __future__ import annotations

import pytest

from oo_ratchet.design.layer_edges import Edge
from oo_ratchet.layers.baseline import LayersBaseline, LayersBaselineError


def test_parse_reads_a_module_map() -> None:
    parsed = LayersBaseline.parse('{"a.x": ["a.y", "a.z"]}', "test")
    assert parsed == {Edge("a.x", "a.y"), Edge("a.x", "a.z")}


@pytest.mark.parametrize(
    "text",
    ["", "{", "[]", '"x"', '{"a": "b"}', '{"a": [1]}', '{"a": {"b": []}}', "null"],
)
def test_parse_refuses_malformed_or_wrong_shape(text: str) -> None:
    with pytest.raises(LayersBaselineError):
        LayersBaseline.parse(text, "test")
