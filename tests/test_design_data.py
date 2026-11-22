"""Syntactic data-placement rules through the public advisory scanner."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from oo_ratchet.design.scanner import DesignScanner

RULES = {"envied-data", "feature-envy", "data-clump", "misplaced-function"}
MODEL = (
    "from dataclasses import dataclass\n@dataclass\n"
    "class Item:\n a: int\n b: int\n c: int\n"
)


def scan(
    tmp_path: Path, sources: dict[str, str], config: str = ""
) -> list[dict[str, object]]:
    root = tmp_path / "pkg"
    root.mkdir(exist_ok=True)
    (root / "__init__.py").write_text("")
    for name, source in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    if config:
        (tmp_path / "pyproject.toml").write_text(config)
    report = json.loads(DesignScanner(root).report.to_json())
    return [row for row in report["findings"] if row["rule"] in RULES]


def symbols(rows: list[dict[str, object]], rule: str) -> set[str]:
    return {str(row["symbol"]) for row in rows if row["rule"] == rule}


@pytest.mark.parametrize(
    "function",
    [
        "def consume(x: Item):\n return x.a + x.b",
        "def consume():\n x: Item = unknown()\n return x.a + x.b",
        "def consume():\n x = Item()\n return x.a + x.b",
    ],
)
def test_envied_receiver_sources(tmp_path: Path, function: str) -> None:
    rows = scan(
        tmp_path,
        {"model.py": MODEL, "consumer.py": "from .model import Item\n" + function},
    )
    assert symbols(rows, "envied-data") == {"Item"}


@pytest.mark.parametrize(
    "body",
    [
        "x = Item()\n x = Item()\n return x.a + x.b + x.c",
        "x: Item = Item()\n x = unknown()\n return x.a + x.b + x.c",
        "x = factory()\n return x.a + x.b + x.c",
        "x = Item()\n y = x\n return y.a + y.b + y.c",
        "def nested(x: Item):\n  return x.a + x.b + x.c\n return 0",
    ],
)
def test_no_inferred_or_reassigned_receivers(tmp_path: Path, body: str) -> None:
    rows = scan(
        tmp_path,
        {
            "model.py": MODEL,
            "consumer.py": "from .model import Item\ndef consume():\n " + body,
        },
    )
    if "nested" not in body:
        assert symbols(rows, "envied-data") == set()
        assert symbols(rows, "feature-envy") == set()
    else:
        assert symbols(rows, "feature-envy") == {"consume.nested"}


@pytest.mark.parametrize(
    "declaration",
    [
        "from typing import NamedTuple\nclass Item(NamedTuple):\n a: int\n b: int",
        "import attrs\n@attrs.define\nclass Item:\n a: int\n b: int",
        "class Item:\n __slots__ = ('a', 'b')",
    ],
)
def test_data_class_shapes(tmp_path: Path, declaration: str) -> None:
    rows = scan(
        tmp_path,
        {
            "model.py": declaration,
            "consumer.py": (
                "from .model import Item\ndef read(x: Item): return x.a + x.b"
            ),
        },
    )
    assert symbols(rows, "envied-data") == {"Item"}


@pytest.mark.parametrize(
    "declaration",
    [
        MODEL + " def total(self): return self.a + self.b",
        "class Item:\n a: int\n b: int",
    ],
)
def test_behavior_and_ordinary_classes_not_envied_data(
    tmp_path: Path, declaration: str
) -> None:
    rows = scan(
        tmp_path,
        {
            "model.py": declaration,
            "consumer.py": (
                "from .model import Item\ndef read(x: Item): return x.a + x.b"
            ),
        },
    )
    assert symbols(rows, "envied-data") == set()


def test_same_module_and_single_field_not_envied(tmp_path: Path) -> None:
    rows = scan(
        tmp_path,
        {
            "model.py": MODEL + "def read(x: Item): return x.a + x.b\n",
            "consumer.py": (
                "from .model import Item\ndef read(x: Item): return x.a + x.a"
            ),
        },
    )
    assert symbols(rows, "envied-data") == set()


@pytest.mark.parametrize(
    "source,expected",
    [
        ("def read(x: Item): return x.a + x.b + x.c", {"read"}),
        (
            "class Reader:\n def read(self, x: Item): return x.a + x.b + x.c + self.a",
            {"Reader.read"},
        ),
        (
            (
                "class Reader:\n def read(self, x: Item):\n"
                "  return x.a + x.b + x.c + self.a + self.b + self.c"
            ),
            set(),
        ),
        (
            (
                "class Reader:\n @classmethod\n"
                " def from_wire(cls, x: Item): return x.a + x.b + x.c"
            ),
            set(),
        ),
        (
            (
                "class Reader:\n @staticmethod\n"
                " def from_wire(x: Item): return x.a + x.b + x.c"
            ),
            {"Reader.from_wire"},
        ),
        ("def read(x: Item):\n x.c = 0\n return x.a + x.b + x.a", set()),
        ("def read(x): return x.a + x.b + x.c", set()),
        ("def read(x: Item):\n x = Item()\n return x.a + x.b + x.c", set()),
    ],
)
def test_feature_envy_threshold_and_exemptions(
    tmp_path: Path, source: str, expected: set[str]
) -> None:
    rows = scan(
        tmp_path,
        {"model.py": MODEL, "consumer.py": "from .model import Item\n" + source},
    )
    assert symbols(rows, "feature-envy") == expected


def test_project_aliases_forward_annotations_and_reexports(tmp_path: Path) -> None:
    rows = scan(
        tmp_path,
        {
            "model.py": MODEL,
            "exports.py": "from .model import Item as Record",
            "consumer.py": (
                "from .exports import Record as Value\n"
                "def read(x: 'Value'): return x.a + x.b + x.c"
            ),
        },
    )
    assert symbols(rows, "envied-data") == {"Item"}
    assert symbols(rows, "feature-envy") == {"read"}


def test_clump_ignores_candidates_requiring_three_way_intersection(
    tmp_path: Path,
) -> None:
    source = "\n".join(
        f"class {name}:\n" + "\n".join(f" {field}: int" for field in fields)
        for name, fields in [("A", "abcdef"), ("B", "abcdeg"), ("C", "abcdfg")]
    )
    rows = [
        row
        for row in scan(tmp_path, {"records.py": source})
        if row["rule"] == "data-clump"
    ]
    assert rows == []


@pytest.mark.parametrize("complement", [False, True], ids=["one-extra", "all-but-one"])
def test_clump_adversarial_thirty_owners_under_one_second(
    tmp_path: Path, complement: bool
) -> None:
    root = tmp_path / "pkg"
    root.mkdir()
    extras = {f"extra_{i}" for i in range(30)}
    classes = []
    for i, extra in enumerate(sorted(extras)):
        fields = {"a", "b", "c", "d"} | (extras - {extra} if complement else {extra})
        classes.append(
            f"class Owner{i}:\n" + "\n".join(f" {name}: int" for name in sorted(fields))
        )
    (root / "records.py").write_text("\n".join(classes))
    code = (
        "import sys\nfrom pathlib import Path\n"
        "from oo_ratchet.design.scanner import DesignScanner\n"
        "print(DesignScanner(Path(sys.argv[1])).report.to_json())"
    )
    start = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-c", code, str(root)],
        capture_output=True,
        text=True,
        timeout=1,
        check=True,
    )
    assert time.monotonic() - start < 1
    rows = [
        r for r in json.loads(result.stdout)["findings"] if r["rule"] == "data-clump"
    ]
    assert len(rows) == (0 if complement else 30)
    assert all(r["detail"] == "a, b, c, d" for r in rows)


def test_clump_keeps_subsets_with_different_owners(tmp_path: Path) -> None:
    source = (
        "class A:\n a:int\n b:int\n c:int\n d:int\n e:int\n"
        "class B(A):\n a:int\n b:int\n c:int\n d:int\n e:int\n"
        "class C(B):\n a:int\n b:int\n c:int\n d:int\n e:int\n"
        "class D:\n a:int\n b:int\n c:int\n d:int"
    )
    rows = [
        row
        for row in scan(tmp_path, {"records.py": source})
        if row["rule"] == "data-clump"
    ]
    assert len(rows) == 7
    assert sum(row["detail"] == "a, b, c, d, e" for row in rows) == 3


def test_clump_mixes_fields_and_signatures(tmp_path: Path) -> None:
    source = (
        "class A:\n a:int\n b:int\n c:int\n d:int\n"
        "def first(a,b,c,d): pass\nclass Service:\n def second(self,a,b,c,d): pass"
    )
    assert symbols(scan(tmp_path, {"data.py": source}), "data-clump") == {
        "A",
        "first",
        "Service.second",
    }


@pytest.mark.parametrize(
    "source",
    [
        "def a(w,x,y,z): pass\ndef b(w,x,y,z): pass",
        "def a(x,y,z): pass\ndef b(x,y,z): pass\ndef c(x,y,z): pass",
    ],
)
def test_clump_minima(tmp_path: Path, source: str) -> None:
    assert symbols(scan(tmp_path, {"data.py": source}), "data-clump") == set()


@pytest.mark.parametrize(
    "source,expected",
    [
        ("def read(x: Item): return 0", {"read"}),
        ("def read(n: int) -> Item:\n x = Item()\n return Item(x.a, x.b, n)", {"read"}),
        ("def read(n: int) -> Item: return Item()", set()),
        ("def create_item(x: Item) -> Item: return x", set()),
        ("def _read(x: Item): return x.a", set()),
        ("class Reader:\n def read(self, x: Item): return x.a", set()),
        ("def read(x: 'broken['): return 0", set()),
    ],
)
def test_misplaced_function(tmp_path: Path, source: str, expected: set[str]) -> None:
    rows = scan(
        tmp_path,
        {"model.py": MODEL, "consumer.py": "from .model import Item\n" + source},
    )
    assert symbols(rows, "misplaced-function") == expected


@pytest.mark.parametrize("layer", ["entry", "adapters"])
def test_layers_skip_data_rules(tmp_path: Path, layer: str) -> None:
    config = f'[tool.oo-ratchet.layers]\n{layer} = ["pkg.*"]'
    rows = scan(
        tmp_path,
        {
            "model.py": MODEL,
            "consumer.py": (
                "from .model import Item\ndef read(x: Item): return x.a + x.b + x.c"
            ),
        },
        config,
    )
    assert rows == []


def test_empty_and_invalid_modules_are_advisory(tmp_path: Path) -> None:
    assert scan(tmp_path, {"empty.py": "", "broken.py": "def invalid("}) == []


def test_nested_body_does_not_type_or_read_outer_receivers(tmp_path: Path) -> None:
    source = (
        "from .model import Item\ndef read(x: Item):\n"
        " def nested(): return x.a + x.b + x.c\n return 0"
    )
    rows = scan(tmp_path, {"model.py": MODEL, "consumer.py": source})
    assert symbols(rows, "envied-data") == set()
    assert symbols(rows, "feature-envy") == set()


def test_local_project_class_and_async_keyword_annotations(tmp_path: Path) -> None:
    rows = scan(
        tmp_path,
        {"model.py": MODEL + "async def read(*, x: 'Item'):\n return x.a + x.b + x.c"},
    )
    assert symbols(rows, "feature-envy") == {"read"}
    assert symbols(rows, "misplaced-function") == set()


def test_qualified_annotation_but_not_qualified_constructor(tmp_path: Path) -> None:
    source = (
        "from . import model\n"
        "def read(x: model.Item): return x.a + x.b + x.c\n"
        "def untyped():\n x = model.Item()\n return x.a + x.b + x.c"
    )
    rows = scan(tmp_path, {"model.py": MODEL, "consumer.py": source})
    assert symbols(rows, "feature-envy") == {"read"}
    assert symbols(rows, "envied-data") == {"Item"}


def test_import_cycles_and_ambiguous_names_do_not_resolve(tmp_path: Path) -> None:
    rows = scan(
        tmp_path,
        {
            "model.py": MODEL,
            "cycle.py": "from .cycle import Again as Again\n",
            "consumer.py": (
                "from .model import Item\nfrom .external import Item\n"
                "from .cycle import Again\ndef read(x: Item, y: Again):\n"
                " return x.a + x.b + x.c + y.a + y.b + y.c"
            ),
        },
    )
    assert rows == []


def test_skipped_owners_do_not_support_clumps(tmp_path: Path) -> None:
    config = '[tool.oo-ratchet.layers]\nadapters = ["pkg.edge"]'
    rows = scan(
        tmp_path,
        {
            "data.py": "def first(a,b,c,d): pass\ndef second(a,b,c,d): pass",
            "edge.py": "def third(a,b,c,d): pass",
        },
        config,
    )
    assert symbols(rows, "data-clump") == set()


@pytest.mark.parametrize(
    "config",
    ["", '[tool.oo-ratchet.layers]\ndomain = ["pkg.*"]', "[tool.oo-ratchet.layers]"],
)
def test_no_config_domain_and_unlayered_are_eligible(
    tmp_path: Path, config: str
) -> None:
    source = "from .model import Item\ndef read(x: Item): return x.a + x.b + x.c"
    rows = scan(tmp_path, {"model.py": MODEL, "edge.py": source}, config)
    assert symbols(rows, "envied-data") == {"Item"}
    assert symbols(rows, "feature-envy") == {"read"}
    assert symbols(rows, "misplaced-function") == {"read"}
