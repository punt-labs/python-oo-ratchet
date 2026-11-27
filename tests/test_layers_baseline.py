"""Parsing the layers baseline: malformed or wrong-shaped JSON is refused."""

from __future__ import annotations

import pytest

from oo_ratchet.core.adapters.edgeformats import EdgeFormat
from oo_ratchet.core.domain.errors import StateError
from oo_ratchet.core.domain.layer_edges import Edge


def test_parse_reads_a_module_map() -> None:
    parsed = EdgeFormat.decode('{"a.x": ["a.y", "a.z"]}', "test")
    assert parsed.edges == {Edge("a.x", "a.y"), Edge("a.x", "a.z")}


@pytest.mark.parametrize(
    "text",
    ["", "{", "[]", '"x"', '{"a": "b"}', '{"a": [1]}', '{"a": {"b": []}}', "null"],
)
def test_parse_refuses_malformed_or_wrong_shape(text: str) -> None:
    with pytest.raises(StateError):
        EdgeFormat.decode(text, "test")
