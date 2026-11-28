"""Lux coupling fixes: order-independent cycle detection and LCOM exemptions."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from oo_ratchet.coupling.graph import ImportGraph
from oo_ratchet.coupling.trees import score_path

_HEADER = "from __future__ import annotations\n\n\n"


class TestCycleMembers:
    """Every node of every cycle is reported, whatever the walk order."""

    def test_three_node_cycle_reports_all_members(self) -> None:
        graph = ImportGraph({"A": {"B", "C"}, "B": {"A"}, "C": {"B"}})
        assert graph.cycle_members() == {"A", "B", "C"}

    def test_two_node_cycle_excludes_bystander(self) -> None:
        graph = ImportGraph({"X": {"Y"}, "Y": {"X"}, "Z": set()})
        assert graph.cycle_members() == {"X", "Y"}

    def test_acyclic_graph(self) -> None:
        assert (
            ImportGraph({"P": {"Q"}, "Q": {"R"}, "R": set()}).cycle_members() == set()
        )

    def test_self_loop(self) -> None:
        assert ImportGraph({"S": {"S"}}).cycle_members() == {"S"}

    def test_disjoint_cycles(self) -> None:
        edges = {"A": {"B"}, "B": {"A"}, "C": {"D"}, "D": {"C"}, "E": set()}
        assert ImportGraph(edges).cycle_members() == {"A", "B", "C", "D"}

    def test_long_chain_does_not_recurse(self) -> None:
        edges = {f"m{i}": {f"m{i + 1}"} for i in range(5000)}
        edges["m5000"] = {"m0"}
        assert len(ImportGraph(edges).cycle_members()) == 5001


_PLAIN = (
    f"{_HEADER}class Store:\n"
    "    def __new__(cls) -> Store:\n"
    "        self = super().__new__(cls)\n"
    "        self._a = 1\n"
    "        self._b = 2\n"
    "        return self\n\n"
    "    def use_a(self) -> int:\n"
    "        return self._a\n\n"
    "    def use_b(self) -> int:\n"
    "        return self._b\n"
)
_BASEMODEL = (
    f"{_HEADER}from pydantic import BaseModel\n\n\n"
    "class Widget(BaseModel):\n"
    "    label: str\n"
    "    tone: str\n\n"
    "    def render(self) -> str:\n"
    "        return self.label\n\n"
    "    def shout(self) -> str:\n"
    "        return self.tone.upper()\n"
)
_FROZEN = (
    f"{_HEADER}from dataclasses import dataclass\n\n\n"
    "@dataclass(frozen=True)\n"
    "class Point:\n"
    "    x: int\n"
    "    y: int\n\n"
    "    def left(self) -> int:\n"
    "        return self.x\n\n"
    "    def top(self) -> int:\n"
    "        return self.y\n"
)
_MARKER = (
    f"{_HEADER}class Separator:\n"
    "    __slots__ = ()\n\n"
    "    def label(self) -> str:\n"
    '        return "---"\n\n'
    "    def item_id(self) -> str:\n"
    '        return ""\n'
)
_SETATTR = (
    f"{_HEADER}class Coord:\n"
    "    __slots__ = ('_x', '_y')\n\n"
    "    def __new__(cls, x: int, y: int) -> Coord:\n"
    "        self = super().__new__(cls)\n"
    '        object.__setattr__(self, "_x", x)\n'
    '        object.__setattr__(self, "_y", y)\n'
    "        return self\n\n"
    "    def use_x(self) -> int:\n"
    "        return self._x\n\n"
    "    def use_y(self) -> int:\n"
    "        return self._y\n"
)


def _max_lcom(tmp_path: Path, sources: dict[str, str]) -> dict[str, float]:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    for stem, src in sources.items():
        (pkg / f"{stem}.py").write_text(src)
    scorer = score_path(pkg, tmp_path)
    return {
        Path(str(r["file"])).stem: cast("float", r["max_lcom"])
        for r in scorer.results
        if "max_lcom" in r
    }


def test_data_shapes_and_stateless_values_are_exempt(tmp_path: Path) -> None:
    lcom = _max_lcom(
        tmp_path,
        {
            "widget": _BASEMODEL,
            "point": _FROZEN,
            "sep": _MARKER,
            "store": _PLAIN,
            "coord": _SETATTR,
        },
    )
    assert lcom["widget"] == 0.0
    assert lcom["point"] == 0.0
    assert lcom["sep"] == 0.0
    assert lcom["store"] > 0.0
    assert lcom["coord"] > 0.0
