"""Primitive public signatures and tag dispatch with distinct layer policies."""

from __future__ import annotations

import ast
from typing import Self

from .data_inventory import DataInventory
from .declaration import Declaration
from .findings import Finding, Rules
from .function_shape import FunctionShape
from .shape import ClassShape
from .tag_switch import TagSwitch
from .type_reference import TypeReference


class SignatureRules:
    """Keep domain-only primitive checks separate from adapter-exempt switches."""

    _inventory: DataInventory
    _layers: dict[str, str | None]

    def __new__(cls, inventory: DataInventory, layers: dict[str, str | None]) -> Self:
        self = super().__new__(cls)
        self._inventory = inventory
        self._layers = layers
        return self

    def findings(self) -> list[Finding]:
        """Return at most one finding per rule and function."""
        return [
            finding
            for owner in self._inventory.declarations()
            if owner.kind != "class"
            for finding in self._function(owner, self._layers)
        ]

    @classmethod
    def _function(
        cls, owner: Declaration, layers: dict[str, str | None]
    ) -> list[Finding]:
        findings = []
        layer = layers.get(owner.module.key)
        if cls._public(owner) and (not layers or layer == "domain"):
            count = sum(cls._primitive(a.annotation) for a in cls._parameters(owner))
            if count >= 2:
                findings.append(
                    owner.finding(
                        Rules.PRIMITIVE_PARAMS, f"primitive parameters={count}"
                    )
                )
        if layer != "adapters" and TagSwitch(FunctionShape(owner)).found():
            findings.append(
                owner.finding(
                    Rules.TAG_SWITCH, "three or more arms dispatch on one tag"
                )
            )
        return findings

    @staticmethod
    def _public(owner: Declaration) -> bool:
        return owner.kind in {"function", "method"} and not any(
            part.startswith("_") for part in owner.symbol.split(".")
        )

    @classmethod
    def _parameters(cls, owner: Declaration) -> list[ast.arg]:
        parameters = FunctionShape(owner).parameters()
        receiver = cls._receiver(owner)
        return [parameter for parameter in parameters if parameter is not receiver]

    @staticmethod
    def _receiver(owner: Declaration) -> ast.arg | None:
        node = owner.node
        if owner.kind != "method" or isinstance(node, ast.ClassDef):
            return None
        positional = node.args.posonlyargs + node.args.args
        if (
            positional
            and positional[0].arg in {"self", "cls"}
            and not any(
                ClassShape._name(d) == "staticmethod" for d in node.decorator_list
            )
        ):
            return positional[0]
        return None

    @classmethod
    def _primitive(cls, annotation: ast.expr | None) -> bool:
        if annotation is None:
            return True
        if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
            try:
                return cls._primitive(ast.parse(annotation.value, mode="eval").body)
            except SyntaxError:
                return False
        if isinstance(annotation, ast.Subscript):
            annotation = annotation.value
        return TypeReference.name(annotation) in {"str", "int", "float", "bool", "dict"}
