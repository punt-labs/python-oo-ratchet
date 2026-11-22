"""Separate expressions evaluated outside a lexical scope from its body."""

from __future__ import annotations

import ast


class ScopeParts:
    """Describe header and body traversal shared by lexical checks."""

    @classmethod
    def split(cls, node: ast.AST) -> tuple[list[ast.AST], list[ast.AST]]:
        """Return enclosing-scope expressions followed by local-scope nodes."""
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body: list[ast.AST] = list(node.body)
            return [
                child for child in ast.iter_child_nodes(node) if child not in body
            ], body
        if isinstance(node, ast.Lambda):
            return [node.args], [node.body]
        if isinstance(
            node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
        ):
            return cls._comprehension(node)
        return [], list(ast.iter_child_nodes(node))

    @staticmethod
    def _comprehension(
        node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp,
    ) -> tuple[list[ast.AST], list[ast.AST]]:
        body: list[ast.AST] = []
        for index, generator in enumerate(node.generators):
            if index:
                body.append(generator.iter)
            body.append(generator.target)
            body.extend(generator.ifs)
        body.extend(
            [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]
        )
        return [node.generators[0].iter], body
