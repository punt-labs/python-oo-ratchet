"""Function signatures and direct attribute loads, without flow inference."""

from __future__ import annotations

import ast
from typing import Self, cast

from .declaration import Declaration
from .shape import ClassShape


class FunctionShape:
    """Read only a function's body, not the bodies of nested declarations."""

    _node: ast.FunctionDef | ast.AsyncFunctionDef

    def __new__(cls, owner: Declaration) -> Self:
        self = super().__new__(cls)
        self._node = cast("ast.FunctionDef | ast.AsyncFunctionDef", owner.node)
        return self

    def parameters(self) -> list[ast.arg]:
        """Return every explicit parameter in signature order."""
        args = self._node.args
        return (
            args.posonlyargs
            + args.args
            + args.kwonlyargs
            + [a for a in (args.vararg, args.kwarg) if a]
        )

    def nodes(self) -> list[ast.AST]:
        """Return structural body nodes, excluding nested defs and lambdas."""
        pending: list[ast.AST] = list(reversed(self._node.body))
        out: list[ast.AST] = []
        while pending:
            node = pending.pop()
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
            ):
                continue
            out.append(node)
            pending.extend(reversed(list(ast.iter_child_nodes(node))))
        return out

    def blocks(self) -> list[list[ast.stmt]]:
        """Return statement blocks without entering nested declaration bodies."""
        blocks = [self._node.body]
        for node in self.nodes():
            blocks.extend(
                cast("list[ast.stmt]", value)
                for _, value in ast.iter_fields(node)
                if isinstance(value, list)
                and value
                and all(isinstance(item, ast.stmt) for item in value)
            )
        return blocks

    def reads(self) -> dict[str, set[str]]:
        """Group direct attribute reads, including augmented assignment targets."""
        reads: dict[str, set[str]] = {}
        for item in self.nodes():
            node = item.target if isinstance(item, ast.AugAssign) else item
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and (isinstance(node.ctx, ast.Load) or isinstance(item, ast.AugAssign))
            ):
                reads.setdefault(node.value.id, set()).add(node.attr)
        return reads

    def decoder(self) -> bool:
        """Return whether this is an explicitly exempt from_* classmethod."""
        return self._node.name.startswith("from_") and any(
            ClassShape._name(d) == "classmethod" for d in self._node.decorator_list
        )
