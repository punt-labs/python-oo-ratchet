"""One advisory design finding and the catalogue of rules that produce them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class Finding:
    """A class or import the design check thinks is worth a human look."""

    rule: str
    path: str
    line: int
    symbol: str
    detail: str

    def as_dict(self) -> dict[str, str | int]:
        """Return the finding as a JSON-serializable row."""
        return {
            "rule": self.rule,
            "path": self.path,
            "line": self.line,
            "symbol": self.symbol,
            "detail": self.detail,
        }


class Rules:
    """The design rules, in report order, with what each one looks for."""

    STATELESS_SINGLE = "stateless-single-method"
    STATELESS_BAG = "stateless-function-bag"
    GETTER_HEAVY = "getter-heavy"
    CONCRETE_IMPORT = "concrete-cross-package-import"
    LAYER_IMPORT = "layer-import"
    DOMAIN_IO = "domain-io"
    UNLAYERED_MODULE = "unlayered-module"
    THICK_ENTRY = "thick-entry"
    ENVIED_DATA = "envied-data"
    FEATURE_ENVY = "feature-envy"
    DATA_CLUMP = "data-clump"
    MISPLACED_FUNCTION = "misplaced-function"

    DESCRIPTIONS: ClassVar[dict[str, str]] = {
        STATELESS_SINGLE: "stateless class with one public method: a function-object",
        STATELESS_BAG: "stateless class with several public methods: a namespace",
        GETTER_HEAVY: "most public members only return a stored field",
        CONCRETE_IMPORT: (
            "stateful concrete class imported across packages, not a Protocol/ABC"
        ),
        LAYER_IMPORT: "module imports a layer further out",
        DOMAIN_IO: "domain module imports IO or calls builtin open",
        UNLAYERED_MODULE: "module matches no declared layer",
        THICK_ENTRY: "entry function has cyclomatic complexity greater than four",
        ENVIED_DATA: "data class fields are read together in another module",
        FEATURE_ENVY: "a typed parameter's attributes dominate a function",
        DATA_CLUMP: "four or more names shared by at least three owners",
        MISPLACED_FUNCTION: "public function belongs on a project class",
    }

    @classmethod
    def ordered(cls) -> tuple[str, ...]:
        """Return the rule ids in report order."""
        return tuple(cls.DESCRIPTIONS)
