"""Which names and expressions of a module are ``pathlib.Path`` objects."""

from __future__ import annotations

import ast
from typing import ClassVar, Self


class PathTypes:
    """Syntactic evidence that a name, attribute or expression is a ``Path``.

    The evidence is whole-module and name-based, like ``BuiltinOpen``: a name
    counts as a path when it is annotated ``Path`` (a parameter, a variable, a
    class attribute or ``self.x``) or assigned a path expression anywhere in the
    module. A path expression is a call of ``Path`` (or ``pathlib.Path``), a
    ``/`` join with a path, a path's ``parent``, or a path method that returns a
    path. ``Path`` is the class imported from ``pathlib``, whether or not the
    import is under ``TYPE_CHECKING``.
    """

    DERIVING: ClassVar[frozenset[str]] = frozenset(
        {
            "with_name",
            "with_suffix",
            "with_stem",
            "joinpath",
            "relative_to",
            "resolve",
            "absolute",
            "expanduser",
            "readlink",
        }
    )
    _classes: set[str]
    _modules: set[str]
    _names: set[str]
    _attrs: set[str]

    def __new__(cls, tree: ast.Module) -> Self:
        self = super().__new__(cls)
        self._classes = set()
        self._modules = set()
        self._names = set()
        self._attrs = set()
        self._imports(tree)
        self._annotated(tree)
        self._assigned(tree)
        return self

    def has_path_class(self) -> bool:
        """Return whether the module names ``pathlib.Path`` at all."""
        return bool(self._classes or self._modules)

    def is_class(self, node: ast.expr) -> bool:
        """Return whether ``node`` is the ``Path`` class itself."""
        if isinstance(node, ast.Name):
            return node.id in self._classes
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "Path"
            and isinstance(node.value, ast.Name)
            and node.value.id in self._modules
        )

    def is_path(self, node: ast.expr) -> bool:
        """Return whether ``node`` is evidenced to be a ``Path`` object."""
        if isinstance(node, ast.Name):
            return node.id in self._names
        if isinstance(node, ast.Attribute):
            return self._attribute(node)
        if isinstance(node, ast.Call):
            return self._call(node)
        if isinstance(node, ast.BinOp):
            return isinstance(node.op, ast.Div) and (
                self.is_path(node.left) or self.is_path(node.right)
            )
        return False

    def _attribute(self, node: ast.Attribute) -> bool:
        if node.attr == "parent":
            return self.is_path(node.value)
        return isinstance(node.value, ast.Name) and node.attr in self._attrs

    def _call(self, node: ast.Call) -> bool:
        if self.is_class(node.func):
            return True
        func = node.func
        return (
            isinstance(func, ast.Attribute)
            and func.attr in self.DERIVING
            and self.is_path(func.value)
        )

    def _imports(self, tree: ast.Module) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "pathlib":
                self._classes.update(
                    a.asname or a.name for a in node.names if a.name == "Path"
                )
            elif isinstance(node, ast.Import):
                self._modules.update(
                    a.asname or a.name for a in node.names if a.name == "pathlib"
                )

    def _annotated(self, tree: ast.Module) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.arg) and self._annotation(node.annotation):
                self._names.add(node.arg)
            elif isinstance(node, ast.AnnAssign) and self._annotation(node.annotation):
                self._bind(node.target)

    def _assigned(self, tree: ast.Module) -> None:
        for _ in range(3):
            before = len(self._names)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and self.is_path(node.value):
                    for target in node.targets:
                        self._bind(target)
            if len(self._names) == before:
                return

    def _bind(self, target: ast.expr) -> None:
        if isinstance(target, ast.Name):
            self._names.add(target.id)
            self._attrs.add(target.id)
        elif isinstance(target, ast.Attribute):
            self._attrs.add(target.attr)

    def _annotation(self, node: ast.expr | None) -> bool:
        if node is None:
            return False
        if self.is_class(node):
            return True
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return self._string(node.value)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return self._annotation(node.left) or self._annotation(node.right)
        if isinstance(node, ast.Subscript) and self._optional(node.value):
            return self._annotation(node.slice)
        if isinstance(node, ast.Tuple):
            return any(self._annotation(elt) for elt in node.elts)
        return False

    @staticmethod
    def _optional(node: ast.expr) -> bool:
        name = node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")
        return name in {"Optional", "Union"}

    def _string(self, text: str) -> bool:
        try:
            return self._annotation(ast.parse(text, mode="eval").body)
        except SyntaxError:
            return False
