"""ClassState holds the class it reads; the old function-bag class is gone."""

from __future__ import annotations

import ast
import importlib

import pytest

from oo_ratchet.coupling.class_state import ClassState


def _cls(source: str) -> ast.ClassDef:
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.ClassDef)
    return node


@pytest.mark.parametrize(
    ("body", "stores_none"),
    [
        ("def f(self): return 1", True),
        ("def f(self): self._x = 1", False),
        ("def f(self): self._x.append(1)", False),
        ("def f(self): self.x = 1", True),
        ("def f(self): object.__setattr__(self, '_x', 1)", False),
        ("def f(self): self.__dict__['_x'] = 1", False),
    ],
)
def test_stores_none_reads_the_held_class(body: str, stores_none: bool) -> None:
    node = _cls(f"class A:\n    {body}\n")
    assert ClassState(node).stores_none() is stores_none


@pytest.mark.parametrize(
    ("body", "stores_nothing"),
    [
        ("def f(self): return 1", True),
        ("def f(self): self.x = 1", False),
        ("def f(self): setattr(self, 'y', 1)", False),
    ],
)
def test_stores_nothing_reads_the_held_class(body: str, stores_nothing: bool) -> None:
    node = _cls(f"class A:\n    {body}\n")
    assert ClassState(node).stores_nothing() is stores_nothing


def test_nested_class_stores_do_not_count() -> None:
    node = _cls("class A:\n    class B:\n        def f(self): self._x = 1\n")
    assert ClassState(node).stores_none()


def test_the_function_bag_class_is_gone() -> None:
    module = importlib.import_module("oo_ratchet.coupling.metrics")
    assert not hasattr(module, "PrivateState")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("oo_ratchet.coupling.private_state")
