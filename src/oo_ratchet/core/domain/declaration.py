"""A syntactic owner of advisory data-design findings."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from .findings import Finding
from .modules import Module


@dataclass(frozen=True, slots=True)
class Declaration:
    """Identify a class or function without line numbers in its symbol key."""

    module: Module
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
    symbol: str
    kind: str
    eligible: bool = True
    """False in a module the data rules skip: the entry and adapter layers."""

    def finding(self, rule: str, detail: str) -> Finding:
        """Attach a rule result to this declaration."""
        return self.module.finding(rule, self.node.lineno, self.symbol, detail)

    def enclosing_class(
        self, classes: dict[tuple[str, str], Declaration]
    ) -> Declaration | None:
        """Return the nearest class declaration that holds this function, if any."""
        if self.kind == "class":
            return None
        prefix = self.symbol.rpartition(".")[0]
        while prefix:
            parent = classes.get((self.module.key, prefix))
            if parent is not None:
                return parent
            prefix = prefix.rpartition(".")[0]
        return None
