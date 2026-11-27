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

    def finding(self, rule: str, detail: str) -> Finding:
        """Attach a rule result to this declaration."""
        return Finding(
            rule, str(self.module.path), self.node.lineno, self.symbol, detail
        )
