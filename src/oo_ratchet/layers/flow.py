"""Which imports can a module-scope name still be bound to, by control flow."""

from __future__ import annotations

import ast
from collections.abc import Callable
from functools import reduce
from typing import Self

type Origin = tuple[str, str]
type Bindings = dict[str, frozenset[Origin]]
type Effect = Callable[[ast.Import | ast.ImportFrom], Bindings]
type Alias = Callable[[ast.stmt, Bindings], Bindings | None]

_LOOPS = (ast.For, ast.AsyncFor, ast.While)
_DEFS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


class BindingFlow:
    """Track, per name, the set of origins any execution path can leave it with.

    A path through ``if``/``try``/``except``/``match``/loops contributes its own
    origins and the sets are joined, so a fallback in an ``except`` cannot erase
    an import that succeeded. A name loses its origins only on an unconditional
    rebinding in the same block: ``=``, ``def``, ``class``, ``import`` or
    ``del`` of the bare name. Annotation without a value and attribute or item
    assignment leave the binding alone. ``imports`` says what an import
    statement binds; the flow supplies everything else. Function and class
    bodies are not entered: their names are bound, their contents are not.
    """

    _imports: Effect
    _alias: Alias | None
    _ever: Bindings

    def __new__(cls, imports: Effect, alias: Alias | None = None) -> Self:
        self = super().__new__(cls)
        self._imports = imports
        self._alias = alias
        self._ever = {}
        return self

    def run(self, body: list[ast.stmt]) -> Bindings:
        """Return the possible origins of each name after ``body`` has run."""
        return self._block(body, {})

    def ever(self, body: list[ast.stmt]) -> Bindings:
        """Return, per name, the origins it had in any state while ``body`` ran."""
        self._ever = {}
        self._block(body, {})
        return self._ever

    def _block(self, body: list[ast.stmt], state: Bindings) -> Bindings:
        for stmt in body:
            state = self._stmt(stmt, state)
            self._ever = self._join(self._ever, state)
        return state

    def _stmt(self, stmt: ast.stmt, state: Bindings) -> Bindings:
        branched = self._branch(stmt, state)
        if branched is not None:
            return branched
        if isinstance(stmt, _LOOPS):
            looped = self._join(state, self._block(stmt.body, state))
            return self._block(stmt.orelse, looped)
        if isinstance(stmt, ast.With | ast.AsyncWith):
            return self._block(stmt.body, state)
        return {**state, **self._effect(stmt, state)}

    def _branch(self, stmt: ast.stmt, state: Bindings) -> Bindings | None:
        if isinstance(stmt, ast.If):
            arms = [self._block(stmt.body, state), self._block(stmt.orelse, state)]
            return reduce(self._join, arms)
        if isinstance(stmt, ast.Try | ast.TryStar):
            return self._try(stmt, state)
        if isinstance(stmt, ast.Match):
            return self._match(stmt, state)
        return None

    def _try(self, stmt: ast.Try | ast.TryStar, state: Bindings) -> Bindings:
        body = self._block(stmt.body, state)
        raised = self._join(state, body)
        arms = [self._block(stmt.orelse, body)]
        arms.extend(self._block(h.body, raised) for h in stmt.handlers)
        return self._block(stmt.finalbody, reduce(self._join, arms))

    def _match(self, stmt: ast.Match, state: Bindings) -> Bindings:
        arms = [self._block(case.body, state) for case in stmt.cases]
        if not any(self._irrefutable(case) for case in stmt.cases):
            arms.append(state)
        return reduce(self._join, arms)

    def _effect(self, stmt: ast.stmt, state: Bindings) -> Bindings:
        if isinstance(stmt, ast.Import | ast.ImportFrom):
            return self._imports(stmt)
        aliased = self._alias(stmt, state) if self._alias else None
        if aliased is not None:
            return aliased
        return {name: frozenset() for name in self.rebound(stmt)}

    @staticmethod
    def _irrefutable(case: ast.match_case) -> bool:
        pattern = case.pattern
        return (
            case.guard is None
            and isinstance(pattern, ast.MatchAs)
            and pattern.pattern is None
        )

    @staticmethod
    def _join(left: Bindings, right: Bindings) -> Bindings:
        return {
            name: left.get(name, frozenset()) | right.get(name, frozenset())
            for name in left.keys() | right.keys()
        }

    @classmethod
    def rebound(cls, stmt: ast.stmt) -> list[str]:
        """Return the bare names ``stmt`` rebinds, unconditionally."""
        if isinstance(stmt, _DEFS):
            return [stmt.name]
        return [
            node.id
            for target in cls._targets(stmt)
            for node in ast.walk(target)
            if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load)
        ]

    @staticmethod
    def _targets(stmt: ast.stmt) -> list[ast.expr]:
        if isinstance(stmt, ast.Assign | ast.Delete):
            return list(stmt.targets)
        if isinstance(stmt, ast.AugAssign):
            return [stmt.target]
        if isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            return [stmt.target]
        return []
