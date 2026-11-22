"""Behavior of the advisory ``oo-ratchet design`` check on small trees."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from oo_ratchet.__main__ import main as cli_main
from oo_ratchet.design.findings import Finding, Rules
from oo_ratchet.design.scanner import DesignScanner

if TYPE_CHECKING:
    import pytest

_WRAPPER = """
class Runner:
    def run(self, x: int) -> int:
        return x + 1
"""

_BAG = """
class Helpers:
    def one(self) -> int:
        return 1

    def two(self) -> int:
        return 2
"""

_STATEFUL = """
class Counter:
    def __init__(self) -> None:
        self._n = 0

    def bump(self) -> int:
        self._n += 1
        return self._n


class Slotted:
    __slots__ = ("_v",)

    def get(self) -> int:
        return 1


class Annotated:
    _v: int

    def get(self) -> int:
        return self._v


class Dynamic:
    def __new__(cls) -> "Dynamic":
        self = super().__new__(cls)
        setattr(self, "_v", 1)
        return self

    def get(self) -> int:
        return 1
"""

_QODO_STATE = """
class Allocated:
    def __new__(cls) -> "Allocated":
        obj = super().__new__(cls)
        obj.value = 1
        return obj

    def get(self) -> int:
        return 1


class DictBacked:
    def put(self, key: str) -> None:
        self.__dict__[key] = 1
"""

_EMPTY_SLOTS = """
class Strings:
    __slots__ = ""

    def run(self) -> int:
        return 1
"""

_SPLIT_INTERFACES = """
from typing import Protocol


class Reader(Protocol):
    def read(self) -> str: ...


class Writer(Protocol):
    def write(self) -> None: ...


class Unrelated:
    def read(self) -> str:
        return ""

    def write(self) -> None:
        return None
"""

_EXEMPT = """
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class Port(Protocol):
    def send(self) -> None: ...


class Base(ABC):
    @abstractmethod
    def go(self) -> None: ...


class Impl(Base):
    def go(self) -> None:
        return None


class Sender:
    def send(self) -> None:
        return None


@dataclass(frozen=True)
class Point:
    x: int

    def norm(self) -> int:
        return self.x


class Colour(Enum):
    RED = 1


class Key:
    def __eq__(self, other: object) -> bool:
        return self is other

    def __hash__(self) -> int:
        return 0
"""

_GETTERS = """
class Record:
    def __init__(self) -> None:
        self._a = 1
        self._b = 2
        self._c = 3

    @property
    def a(self) -> int:
        return self._a

    @property
    def b(self) -> int:
        return self._b

    def get_c(self) -> int:
        return self._c

    def total(self) -> int:
        return self._a + self._b + self._c
"""

_ENGINE = """
class Engine:
    def __init__(self) -> None:
        self._rpm = 0

    def spin(self) -> int:
        return self._rpm


class Wrapper:
    __slots__ = ("_data", "_where")
    _data: dict[str, int]
    _where: "str | None"

    def __new__(cls, data: dict[str, int]) -> "Wrapper":
        self = super().__new__(cls)
        self._data = data
        return self

    def require(self, key: str) -> int:
        return self._data[key]


class Mutable:
    __slots__ = ("_n",)
    _n: int

    def __init__(self) -> None:
        self._n = 0

    def bump(self) -> None:
        self._n += 1


class Handle:
    __slots__ = ("_path",)
    _path: Path

    def __new__(cls, path: Path) -> "Handle":
        self = super().__new__(cls)
        self._path = path
        return self


class EngineValue:
    def __eq__(self, other: object) -> bool:
        return self is other

    def __hash__(self) -> int:
        return 0
"""

_CAR = """
from typing import TYPE_CHECKING

from pkg.engine.core import Engine, EngineValue, Mutable, Wrapper, Handle
from ..engine import Engine as Reexported
from pkg.engine import PublicEngine

if TYPE_CHECKING:
    from pkg.engine.core import Engine as TypedEngine

from .wheel import Wheel
"""

_WHEEL = """
class Wheel:
    def __init__(self) -> None:
        self._size = 1

    def size(self) -> int:
        return self._size
"""


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "pkg"
    for rel, text in {"__init__.py": "", **files}.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def _findings(root: Path) -> list[Finding]:
    return _json_findings(DesignScanner(root).report.to_json())


def _json_findings(text: str) -> list[Finding]:
    return [Finding(**row) for row in json.loads(text)["findings"]]


def _symbols(findings: list[Finding], rule: str) -> set[str]:
    return {f.symbol for f in findings if f.rule == rule}


def test_stateless_single_method_class_is_flagged(tmp_path: Path) -> None:
    found = _findings(_tree(tmp_path, {"w.py": _WRAPPER}))
    assert _symbols(found, Rules.STATELESS_SINGLE) == {"Runner"}


def test_stateless_function_bag_is_flagged(tmp_path: Path) -> None:
    found = _findings(_tree(tmp_path, {"b.py": _BAG}))
    assert _symbols(found, Rules.STATELESS_BAG) == {"Helpers"}


def test_every_kind_of_state_suppresses_stateless_rules(tmp_path: Path) -> None:
    found = _findings(_tree(tmp_path, {"s.py": _STATEFUL}))
    assert _symbols(found, Rules.STATELESS_SINGLE) == set()


def test_new_local_and_dict_writes_are_state(tmp_path: Path) -> None:
    found = _findings(_tree(tmp_path, {"q.py": _QODO_STATE}))
    assert _symbols(found, Rules.STATELESS_SINGLE) == set()


def test_empty_string_slots_are_not_state(tmp_path: Path) -> None:
    found = _findings(_tree(tmp_path, {"s.py": _EMPTY_SLOTS}))
    assert _symbols(found, Rules.STATELESS_SINGLE) == {"Strings"}


def test_methods_split_across_interfaces_do_not_exempt(tmp_path: Path) -> None:
    found = _findings(_tree(tmp_path, {"i.py": _SPLIT_INTERFACES}))
    assert _symbols(found, Rules.STATELESS_BAG) == {"Unrelated"}


def test_interfaces_value_types_and_implementations_are_exempt(
    tmp_path: Path,
) -> None:
    found = _findings(_tree(tmp_path, {"e.py": _EXEMPT}))
    assert found == []


def test_getter_heavy_class_is_flagged(tmp_path: Path) -> None:
    found = _findings(_tree(tmp_path, {"g.py": _GETTERS}))
    assert _symbols(found, Rules.GETTER_HEAVY) == {"Record"}


def test_concrete_cross_package_imports(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "engine/__init__.py": (
                "from .core import Engine\nfrom .core import Engine as PublicEngine\n"
            ),
            "engine/core.py": _ENGINE,
            "car/__init__.py": "",
            "car/body.py": _CAR,
            "car/wheel.py": _WHEEL,
        },
    )
    rows = [f for f in _findings(root) if f.rule == Rules.CONCRETE_IMPORT]
    assert sorted(f.symbol for f in rows) == [
        "Engine",
        "Engine",
        "Engine",
        "Handle",
        "Mutable",
        "PublicEngine",
    ]
    assert all(f.path.endswith("body.py") for f in rows)
    assert any("PublicEngine" in f.detail for f in rows)
    assert sum("type-only" in f.detail for f in rows) == 1


def test_cli_is_advisory_and_emits_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _tree(tmp_path, {"w.py": _WRAPPER})
    assert cli_main(["design", str(root), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["advisory"] is True
    assert doc["counts"][Rules.STATELESS_SINGLE] == 1


def test_cli_text_report_and_missing_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _tree(tmp_path, {"w.py": _WRAPPER})
    assert cli_main(["design", str(root)]) == 0
    assert "Runner" in capsys.readouterr().out
    assert cli_main(["design", str(tmp_path / "missing")]) == 2


def test_dispatcher_usage_and_unknown_gate(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main([]) == 2
    assert cli_main(["--help"]) == 0
    assert "design" in capsys.readouterr().out
    assert cli_main(["nope"]) == 2
