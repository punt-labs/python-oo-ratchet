"""Public-scanner checks for syntactic design shape rules and Tier 0 caps."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oo_ratchet.design.scanner import DesignScanner

RULES = {"primitive-params", "tag-switch", "middle-man", "split-cohesion", "size-cap"}


def scan(tmp_path: Path, source: str, layer: str = "") -> list[dict[str, object]]:
    root = tmp_path / "pkg"
    root.mkdir()
    (root / "model.py").write_text(source)
    if layer:
        glob = "elsewhere.*" if layer == "unlayered" else "pkg.*"
        key = "domain" if layer == "unlayered" else layer
        (tmp_path / "pyproject.toml").write_text(
            f'[tool.oo-ratchet.layers]\n{key} = ["{glob}"]\n'
        )
    doc = json.loads(DesignScanner(root).report.to_json())
    return [row for row in doc["findings"] if row["rule"] in RULES]


def symbols(rows: list[dict[str, object]], rule: str) -> set[str]:
    return {str(row["symbol"]) for row in rows if row["rule"] == rule}


@pytest.mark.parametrize(
    "decorator", ["property", "cached_property", "functools.cached_property"]
)
@pytest.mark.parametrize("mixed", [False, True])
def test_lcom4_callable_property_is_a_field(
    tmp_path: Path, decorator: str, mixed: bool
) -> None:
    source = (
        f"class C:\n @{decorator}\n def handler(self): return self._cb\n"
        " def a(self): return self.handler()\n"
        + (
            " def b(self): return self.handler\n"
            if mixed
            else " def b(self): self.handler(1)\n"
        )
        + " def c(self): return self.handler(2)"
    )
    assert not symbols(scan(tmp_path, source), "split-cohesion")


def test_lcom4_callable_property_with_setter_and_deleter(tmp_path: Path) -> None:
    source = (
        "class C:\n @property\n def handler(self): return self._cb\n"
        " @handler.setter\n def handler(self, value): self._cb=value\n"
        " @handler.deleter\n def handler(self): del self._cb\n"
        " def a(self): self.handler()\n def b(self): self.handler(1)\n"
        " def c(self): self.handler(2)"
    )
    assert not symbols(scan(tmp_path, source), "split-cohesion")


@pytest.mark.parametrize(
    "values,expected",
    [
        (["'a'", "'b'", "'c'", "fallback"], {"fee"}),
        (["fallback", "'a'", "'b'", "'c'", "fallback"], {"fee"}),
        (["Kind.A", "Kind.B", "Kind.C", "fallback"], {"fee"}),
        (["'a'", "'b'", "fallback", "'c'"], set()),
        (["'a'", "fallback", "'b'", "'c'"], set()),
        (["fallback", "'a'", "'b'", "'c'"], {"fee"}),
        ([], set()),
        (["fallback"] * 4, set()),
    ],
)
def test_tag_switch_consecutive_literal_runs(
    tmp_path: Path, values: list[str], expected: set[str]
) -> None:
    arms = "\n".join(
        f" {'if' if i == 0 else 'elif'} kind == {value}: return 1"
        for i, value in enumerate(values)
    )
    source = "def fee(kind, fallback):\n" + (arms or " pass")
    assert symbols(scan(tmp_path, source), "tag-switch") == expected


@pytest.mark.parametrize("mixed", [False, True])
def test_lcom4_shared_callable_field(tmp_path: Path, mixed: bool) -> None:
    body = (
        "class C:\n def a(self): return self._cb()\n"
        + (
            " def b(self): return self._cb\n"
            if mixed
            else " def b(self): self._cb(1)\n"
        )
        + " def c(self): return self._cb(2)"
    )
    assert not symbols(scan(tmp_path, body), "split-cohesion")


def test_lcom4_different_callable_fields_stay_disconnected(tmp_path: Path) -> None:
    body = "class C:\n" + "\n".join(
        f" def {name}(self): return self._{name}()" for name in ("a", "b", "c")
    )
    rows = scan(tmp_path, body)
    assert next(r["detail"] for r in rows if r["rule"] == "split-cohesion") == "LCOM4=3"


def context_source(kind: str, parameters: str) -> str:
    definition = f"def f({parameters}): pass"
    if kind == "function":
        return definition
    decorator = "" if kind == "instance" else f" @{kind}method\n"
    return "class C:\n" + decorator + " " + definition


@pytest.mark.parametrize("name", ["self", "cls"])
@pytest.mark.parametrize("kind", ["function", "static", "instance", "class"])
def test_size_cap_receiver_context(tmp_path: Path, name: str, kind: str) -> None:
    parameters = f"{name}:Value," + ",".join(f"p{i}:Value" for i in range(5))
    expected = (
        {"f" if kind == "function" else "C.f"}
        if kind in {"function", "static"}
        else set()
    )
    assert (
        symbols(scan(tmp_path, context_source(kind, parameters)), "size-cap")
        == expected
    )


@pytest.mark.parametrize("name", ["self", "cls"])
@pytest.mark.parametrize("kind", ["function", "static", "instance", "class"])
def test_primitive_receiver_context(tmp_path: Path, name: str, kind: str) -> None:
    source = context_source(kind, f"{name}:str,other:int")
    expected = (
        {"f" if kind == "function" else "C.f"}
        if kind in {"function", "static"}
        else set()
    )
    assert symbols(scan(tmp_path, source), "primitive-params") == expected


@pytest.mark.parametrize(
    "annotation,expected",
    [
        ("'dict[str, int]'", {"f"}),
        ("'dict[str, list[int]]'", {"f"}),
        ("'list[str]'", set()),
        ("'dict['", set()),
        ("''", set()),
    ],
)
def test_quoted_generic_primitive_annotations(
    tmp_path: Path, annotation: str, expected: set[str]
) -> None:
    source = f"def f(a:{annotation},b:str): pass"
    assert symbols(scan(tmp_path, source), "primitive-params") == expected


@pytest.mark.parametrize(
    "source,expected",
    [
        ("def f(a: str,b: int): pass", {"f"}),
        ("def f(a,b): pass", {"f"}),
        ("def f(a: 'str',b: dict[str,int]): pass", {"f"}),
        ("async def f(a: float,*,b: bool): pass", {"f"}),
        ("class C:\n def f(self,a:int,b:str): pass", {"C.f"}),
        ("class C:\n @classmethod\n def f(cls,a:int,b:str): pass", {"C.f"}),
        ("class C:\n @staticmethod\n def f(a:int,b:str): pass", {"C.f"}),
        ("def f(a: str,b: Value): pass", set()),
        ("def f(): pass", set()),
        ("def _f(a: int,b: str): pass", set()),
        ("class C:\n def f(self,a:int): pass", set()),
        ("class C:\n def __init__(self,a:int,b:str): pass", set()),
        ("def outer():\n def inner(a:int,b:str): pass", set()),
    ],
)
def test_primitive_signatures(tmp_path: Path, source: str, expected: set[str]) -> None:
    assert symbols(scan(tmp_path, source), "primitive-params") == expected


@pytest.mark.parametrize(
    "layer,expected",
    [
        ("", {"f"}),
        ("domain", {"f"}),
        ("application", set()),
        ("entry", set()),
        ("adapters", set()),
        ("unlayered", set()),
    ],
)
def test_primitive_domain_only_when_configured(
    tmp_path: Path, layer: str, expected: set[str]
) -> None:
    assert (
        symbols(scan(tmp_path, "def f(a:int,b:str): pass", layer), "primitive-params")
        == expected
    )


CHAIN = (
    "if kind == 'a': return 1\n elif kind == 'b': return 2\n"
    " elif kind == 'c': return 3\n else: return 0"
)


@pytest.mark.parametrize(
    "body,expected",
    [
        (CHAIN, {"fee"}),
        (
            (
                "if K.A == obj.kind: pass\n elif obj.kind == K.B: pass\n"
                " elif obj.kind == K.C: pass"
            ),
            {"fee"},
        ),
        (
            (
                "match kind:\n  case 'a': pass\n  case 'b': pass\n"
                "  case 'c': pass\n  case _: pass"
            ),
            {"fee"},
        ),
        (
            "match obj.kind:\n  case K.A: pass\n  case K.B: pass\n  case K.C: pass",
            {"fee"},
        ),
        ("match kind:\n  case 1 | 2 | 3: pass\n  case _: pass", set()),
        ("if kind == 'a': pass\n elif kind == 'b': pass\n else: pass", set()),
        ("if x == 'a': pass\n elif y == 'b': pass\n elif z == 'c': pass", set()),
        ("if kind > 1: pass\n elif kind > 2: pass\n elif kind > 3: pass", set()),
        ("return 0", set()),
    ],
)
def test_tag_switch_forms(tmp_path: Path, body: str, expected: set[str]) -> None:
    assert symbols(scan(tmp_path, "def fee(kind):\n " + body), "tag-switch") == expected


@pytest.mark.parametrize("layer", ["", "domain", "entry", "application", "adapters"])
def test_tag_switch_adapter_exemption(tmp_path: Path, layer: str) -> None:
    expected = set() if layer == "adapters" else {"fee"}
    assert (
        symbols(scan(tmp_path, "def fee(kind):\n " + CHAIN, layer), "tag-switch")
        == expected
    )


FACADE = (
    "class Facade{base}:\n def first(self,x): return self._worker.first(x)\n"
    " def second(self,x): return self._worker.second(x)\n"
)


@pytest.mark.parametrize(
    "prelude,base,expected",
    [
        ("from typing import Protocol as P\n", "P", set()),
        ("from typing_extensions import Protocol as P\n", "P", set()),
        ("from typing import Protocol as P\n", "P[T]", set()),
        ("if TYPE_CHECKING:\n from typing import Protocol as P\n", "P", set()),
        ("from typing import Protocol as P\nclass Port(P): pass\n", "Port", set()),
        ("from typing import Protocol as P\nP = object\n", "P", {"Facade"}),
        ("def f():\n from typing import Protocol as P\n", "P", {"Facade"}),
        ("from .typing import Protocol as P\n", "P", {"Facade"}),
    ],
)
def test_middle_man_protocol_import_aliases(
    tmp_path: Path, prelude: str, base: str, expected: set[str]
) -> None:
    source = prelude + FACADE.format(base=f"({base})")
    assert symbols(scan(tmp_path, source), "middle-man") == expected


@pytest.mark.parametrize(
    "prelude,base,expected",
    [
        ("from typing import Protocol\n", "Protocol", set()),
        ("from typing_extensions import Protocol\n", "Protocol", set()),
        ("import typing\n", "typing.Protocol", set()),
        ("import typing as t\n", "t.Protocol[T]", set()),
        ("import typing_extensions as t\n", "t.Protocol", set()),
        ("import typing as t\nclass Port(t.Protocol): pass\n", "Port", set()),
        ("import typing as t\ndef helper(t): pass\n", "t.Protocol", set()),
        ("import typing as t\ndef helper(): t = None\n", "t.Protocol", set()),
        ("", "Protocol", {"Facade"}),
        ("class Protocol: pass\n", "Protocol", {"Facade"}),
        ("from other import Protocol\n", "Protocol", {"Facade"}),
        ("import other\n", "other.Protocol", {"Facade"}),
        ("import other as t\n", "t.Protocol", {"Facade"}),
        ("from .typing import Protocol\n", "Protocol", {"Facade"}),
        ("import typing as t\nt = object\n", "t.Protocol", {"Facade"}),
        ("from typing import Protocol\nProtocol = object\n", "Protocol", {"Facade"}),
        ("from typing import Protocol\nclass Protocol: pass\n", "Protocol", {"Facade"}),
        ("import typing\ndef typing(): pass\n", "typing.Protocol", {"Facade"}),
        ("import typing\nimport typing\n", "typing.Protocol", {"Facade"}),
        (
            "from typing import Protocol\nif True: Protocol = None\n",
            "Protocol",
            {"Facade"},
        ),
        (
            "from typing import Protocol\ntry:\n Protocol = object\nexcept: pass\n",
            "Protocol",
            {"Facade"},
        ),
        (
            "def helper():\n import typing as t\n",
            "t.Protocol",
            {"Facade"},
        ),
        (
            "class Protocol: pass\nclass Port(Protocol): pass\n",
            "Port",
            {"Facade"},
        ),
    ],
)
def test_middle_man_requires_standard_protocol_binding(
    tmp_path: Path, prelude: str, base: str, expected: set[str]
) -> None:
    source = prelude + FACADE.format(base=f"({base})")
    assert symbols(scan(tmp_path, source), "middle-man") == expected


@pytest.mark.parametrize(
    "base,prelude,expected",
    [
        ("", "", {"Facade"}),
        ("(Protocol)", "from typing import Protocol\n", set()),
        ("(typing.Protocol)", "import typing\n", set()),
        ("(Port)", "from typing import Protocol\nclass Port(Protocol): pass\n", set()),
        ("(Port)", "import typing\nclass Port(typing.Protocol[T]): pass\n", set()),
        ("(Base)", "class Base: pass\n", {"Facade"}),
    ],
)
def test_middle_man_and_protocol_exemptions(
    tmp_path: Path, base: str, prelude: str, expected: set[str]
) -> None:
    assert (
        symbols(scan(tmp_path, prelude + FACADE.format(base=base)), "middle-man")
        == expected
    )


@pytest.mark.parametrize(
    "body,expected",
    [
        (
            (
                "def first(self,x): self._worker.first(x)\n"
                " def second(self,x): self._worker.second(x)"
            ),
            {"Facade"},
        ),
        (
            (
                "async def first(self,x): return await self._worker.first(x)\n"
                " async def second(self,x): await self._worker.second(x)"
            ),
            {"Facade"},
        ),
        ("def first(self,x): return self._worker.first(x)", set()),
        (
            (
                "def first(self,x): return self._a.first(x)\n"
                " def second(self,x): return self._b.second(x)"
            ),
            set(),
        ),
        (
            (
                "def first(self,x): return self._worker.first(tweak(x))\n"
                " def second(self,x): return self._worker.second(x)"
            ),
            set(),
        ),
        (
            (
                "def first(self,x):\n  x += 1\n  return self._worker.first(x)\n"
                " def second(self,x): return self._worker.second(x)"
            ),
            set(),
        ),
    ],
)
def test_middle_man_requires_two_single_calls_to_same_field(
    tmp_path: Path, body: str, expected: set[str]
) -> None:
    assert symbols(scan(tmp_path, "class Facade:\n " + body), "middle-man") == expected


@pytest.mark.parametrize(
    "body,expected",
    [
        (
            (
                "def a(self): return self.x\n def b(self): return self.y\n"
                " def c(self): return self.z"
            ),
            {"C"},
        ),
        (
            (
                "def a(self): return self.x\n def b(self): return self.x+self.y\n"
                " def c(self): return self.y"
            ),
            set(),
        ),
        (
            (
                "def a(self): return self.helper()\n"
                " def b(self): return self.helper()\n"
                " def helper(self): return 1"
            ),
            set(),
        ),
        ("def a(self): return self.x\n def b(self): return self.y", set()),
        (
            (
                "def a(self): return self.x\n @staticmethod\n def b(): return 1\n"
                " @classmethod\n def c(cls): return 2"
            ),
            set(),
        ),
    ],
)
def test_lcom4_shared_fields_calls_and_minimum_methods(
    tmp_path: Path, body: str, expected: set[str]
) -> None:
    assert symbols(scan(tmp_path, "class C:\n " + body), "split-cohesion") == expected


@pytest.mark.parametrize("initializer", ["__init__", "__new__", "__post_init__"])
def test_lcom4_initializers_do_not_connect_or_count(
    tmp_path: Path, initializer: str
) -> None:
    body = (
        f"class C:\n def {initializer}(self): self.x=self.y=self.z=0\n"
        " def a(self): return self.x\n def b(self): return self.y\n"
        " def c(self): return self.z"
    )
    rows = scan(tmp_path, body)
    assert symbols(rows, "split-cohesion") == {"C"}
    assert next(r["detail"] for r in rows if r["rule"] == "split-cohesion") == "LCOM4=3"


@pytest.mark.parametrize("count,expected", [(400, set()), (401, {"<module>"})])
def test_module_size_cap(tmp_path: Path, count: int, expected: set[str]) -> None:
    assert symbols(scan(tmp_path, "value = 0\n" * count), "size-cap") == expected


@pytest.mark.parametrize("count,expected", [(25, set()), (26, {"C"})])
def test_method_count_cap(tmp_path: Path, count: int, expected: set[str]) -> None:
    source = "class C:\n" + "\n".join(
        f" def m{i}(self): return self.value" for i in range(count)
    )
    assert symbols(scan(tmp_path, source), "size-cap") == expected


@pytest.mark.parametrize("count,expected", [(5, set()), (6, {"f"})])
def test_parameter_cap(tmp_path: Path, count: int, expected: set[str]) -> None:
    args = ",".join(f"p{i}:Value" for i in range(count))
    assert symbols(scan(tmp_path, f"def f({args}): pass"), "size-cap") == expected


@pytest.mark.parametrize("count,expected", [(10, set()), (11, {"f"})])
def test_complexity_cap(tmp_path: Path, count: int, expected: set[str]) -> None:
    source = "def f(x):\n" + "\n".join(f" if x == {i}: pass" for i in range(count - 1))
    assert symbols(scan(tmp_path, source), "size-cap") == expected


@pytest.mark.parametrize("source", ["", "def broken("])
def test_empty_or_invalid_source_is_safe(tmp_path: Path, source: str) -> None:
    assert scan(tmp_path, source) == []


@pytest.mark.parametrize("terminal", ["return 1", "raise ValueError()"])
def test_contiguous_terminal_if_arms(tmp_path: Path, terminal: str) -> None:
    body = "\n".join(f" if kind == {i}: {terminal}" for i in range(3))
    assert symbols(scan(tmp_path, "def fee(kind):\n" + body), "tag-switch") == {"fee"}


@pytest.mark.parametrize(
    "middle", [" pass\n", " if other: return 1\n", " for x in xs:\n  pass\n"]
)
def test_early_return_arms_cannot_cross_other_statements(
    tmp_path: Path, middle: str
) -> None:
    body = (
        " if kind == 1: return 1\n"
        + middle
        + " if kind == 2: return 2\n if kind == 3: return 3"
    )
    assert not symbols(scan(tmp_path, "def fee(kind):\n" + body), "tag-switch")


def test_early_return_arms_do_not_cross_nested_function_bodies(tmp_path: Path) -> None:
    source = (
        "def fee(kind):\n if kind == 1: return 1\n"
        " def nested():\n  if kind == 2: return 2\n  if kind == 3: return 3"
    )
    assert not symbols(scan(tmp_path, source), "tag-switch")


def test_early_return_chain_inside_nested_block(tmp_path: Path) -> None:
    source = (
        "def fee(kind):\n try:\n"
        + "\n".join(f"  if kind == {i}: return {i}" for i in range(3))
        + "\n except ValueError:\n  return 0"
    )
    assert symbols(scan(tmp_path, source), "tag-switch") == {"fee"}


@pytest.mark.parametrize(
    "decorator",
    [
        "property",
        "cached_property",
        "functools.cached_property",
        "value.setter",
        "value.deleter",
    ],
)
def test_lcom4_accessors_do_not_count_as_methods(
    tmp_path: Path, decorator: str
) -> None:
    source = "class C:\n" + "\n".join(
        f" @{decorator}\n def {name}(self): return self._{name}"
        for name in ("a", "b", "c")
    )
    assert not symbols(scan(tmp_path, source), "split-cohesion")


def test_lcom4_accessor_body_cannot_connect_business_methods(tmp_path: Path) -> None:
    source = (
        "class C:\n @property\n def data(self): return self.x+self.y+self.z\n"
        " def a(self): return self.x\n def b(self): return self.y\n"
        " def c(self): return self.z"
    )
    rows = scan(tmp_path, source)
    assert next(r["detail"] for r in rows if r["rule"] == "split-cohesion") == "LCOM4=3"


@pytest.mark.parametrize("initializer", ["__init__", "__new__", "__post_init__"])
def test_lcom4_initializers_cannot_reach_three_method_threshold(
    tmp_path: Path, initializer: str
) -> None:
    source = (
        f"class C:\n def {initializer}(self): pass\n"
        " def a(self): return self.x\n def b(self): return self.y"
    )
    assert not symbols(scan(tmp_path, source), "split-cohesion")


def test_lcom4_nested_body_does_not_add_edges(tmp_path: Path) -> None:
    source = (
        "class C:\n def a(self):\n  def inner(): return self.y\n  return self.x\n"
        " def b(self): return self.y\n def c(self): return self.x"
    )
    rows = scan(tmp_path, source)
    assert next(r["detail"] for r in rows if r["rule"] == "split-cohesion") == "LCOM4=2"


def test_size_cap_combines_function_measures(tmp_path: Path) -> None:
    source = "def f(a:Value,b:Value,c:Value,d:Value,e:Value,f:Value):\n" + "\n".join(
        f" if a == {i}: pass" for i in range(10)
    )
    rows = [r for r in scan(tmp_path, source) if r["rule"] == "size-cap"]
    assert len(rows) == 1
    assert rows[0]["detail"] == "params=6 > 5; complexity=11 > 10"


def test_size_cap_excludes_posonly_receiver_and_variadics(tmp_path: Path) -> None:
    source = (
        "class C:\n"
        " def f(self,a:Value,b:Value,c:Value,d:Value,e:Value,/,*args,**kwargs): pass"
    )
    assert not symbols(scan(tmp_path, source), "size-cap")


def test_size_cap_uses_code_lines_not_docstrings_or_comments(tmp_path: Path) -> None:
    source = '"""\n' + "doc\n" * 401 + '"""\n' + "# comment\n" * 500 + "value=0\n" * 400
    assert not symbols(scan(tmp_path, source), "size-cap")
