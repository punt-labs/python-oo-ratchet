"""One advisory design finding and the catalogue of rules that produce them."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, nonmember


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


class Rules(StrEnum):
    """The design rules, in report order, each with what it looks for."""

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
    PRIMITIVE_PARAMS = "primitive-params"
    TAG_SWITCH = "tag-switch"
    MIDDLE_MAN = "middle-man"
    SPLIT_COHESION = "split-cohesion"
    SIZE_CAP = "size-cap"

    # Rules measured right at least 90% of the time on vox, quarry, lux and
    # z-spec (docs/architecture/b4-design-precision.md). ``--enforce`` blocks on
    # an added key of these rules and no others.
    GATE_CAPABLE = nonmember(
        frozenset(
            {
                "layer-import",
                "size-cap",
                "thick-entry",
                "unlayered-module",
                "stateless-single-method",
            }
        )
    )

    @property
    def description(self) -> str:
        """Return what the rule looks for."""
        return _DESCRIPTIONS[self]

    @classmethod
    def ordered(cls) -> tuple[Rules, ...]:
        """Return the rules in report order."""
        return tuple(cls)


_DESCRIPTIONS: dict[str, str] = {
    "stateless-single-method": (
        "stateless class with one public method: a function-object"
    ),
    "stateless-function-bag": (
        "stateless class with several public methods: a namespace"
    ),
    "getter-heavy": "most public members only return a stored field",
    "concrete-cross-package-import": (
        "stateful concrete class imported across packages, not a Protocol/ABC"
    ),
    "layer-import": "module imports a layer further out",
    "domain-io": "domain module imports IO or calls builtin open",
    "unlayered-module": "module matches no declared layer",
    "thick-entry": "entry function has cyclomatic complexity greater than four",
    "envied-data": "data class fields are read together in another module",
    "feature-envy": "a typed parameter's attributes dominate a function",
    "data-clump": "four or more names shared by at least three owners",
    "misplaced-function": "public function belongs on a project class",
    "primitive-params": "public signature has at least two primitive parameters",
    "tag-switch": "three or more arms dispatch on the same tag",
    "middle-man": "public methods only forward to one collaborator",
    "split-cohesion": "instance methods form disconnected LCOM4 components",
    "size-cap": "symbol exceeds a Tier 0 size or complexity ceiling",
}
