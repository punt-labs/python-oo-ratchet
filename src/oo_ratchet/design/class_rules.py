"""The per-class design rules: stateless wrappers and getter-heavy classes."""

from __future__ import annotations

from typing import ClassVar, Self

from .findings import Finding, Rules
from .modules import Module
from .shape import ClassShape


class ClassRules:
    """Apply the class-shape rules to every class in one module.

    A stateless class is skipped when it subclasses something (it takes part in
    an inheritance hierarchy) or when every public method it has is declared by
    an abstract class in the tree (a strategy implementing an interface).
    """

    GETTER_MIN: ClassVar[int] = 3
    GETTER_SHARE: ClassVar[float] = 0.5

    _interface: frozenset[str]

    def __new__(cls, interface_methods: frozenset[str]) -> Self:
        self = super().__new__(cls)
        self._interface = interface_methods
        return self

    def findings(self, module: Module) -> list[Finding]:
        """Return the class-rule findings for ``module``."""
        out: list[Finding] = []
        for shape in module.classes.values():
            if shape.is_exempt or shape.is_abstract:
                continue
            for rule, detail in (self._stateless(shape), self._getters(shape)):
                if rule:
                    out.append(
                        Finding(rule, str(module.path), shape.line, shape.name, detail)
                    )
        return out

    def _stateless(self, shape: ClassShape) -> tuple[str, str]:
        methods = shape.public_methods()
        if not methods or shape.is_subclass or shape.has_state:
            return "", ""
        if all(m in self._interface for m in methods):
            return "", ""
        listed = ", ".join(methods[:4]) + (", ..." if len(methods) > 4 else "")
        if len(methods) == 1:
            return Rules.STATELESS_SINGLE, f"only public method: {listed}"
        return Rules.STATELESS_BAG, f"{len(methods)} public methods: {listed}"

    def _getters(self, shape: ClassShape) -> tuple[str, str]:
        getters = shape.accessors()
        members = shape.public_members()
        if len(getters) < self.GETTER_MIN or len(getters) < members * self.GETTER_SHARE:
            return "", ""
        return Rules.GETTER_HEAVY, (
            f"{len(getters)} of {members} public members only return a field"
        )
