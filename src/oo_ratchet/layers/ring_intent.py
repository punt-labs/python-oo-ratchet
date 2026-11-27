"""Where a ring comes from when nobody imported it: a marker, a table, a name."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Self

from oo_ratchet.design.layer_config import LayerConfig, LayerConfigError

from .suggest_model import ModuleFacts

RINGS = ("entry", "adapters", "application", "domain")


@dataclass(frozen=True, slots=True)
class Intent:
    """A ring someone declared or named, and the source that says so.

    ``ring`` is ``None`` when the source could not be used; ``source`` then
    says why.
    """

    ring: str | None
    source: str


class NameConvention:
    """Package names that suggest a ring: ``domain/`` suggests ``domain``.

    A module is matched by every dotted segment below the package root. Two
    segments that suggest different rings are ambiguous, so the module gets no
    ring from its name.
    """

    DEFAULTS: ClassVar[dict[str, tuple[str, ...]]] = {
        "domain": ("domain", "model", "models", "core"),
        "application": ("application", "usecases", "use_cases"),
        "adapters": ("adapters", "adapter", "infra", "infrastructure"),
    }
    _names: dict[str, tuple[str, ...]]

    def __new__(cls, overrides: dict[str, object] | None = None) -> Self:
        self = super().__new__(cls)
        self._names = {**cls.DEFAULTS, **cls._checked(overrides or {})}
        return self

    @staticmethod
    def _checked(table: dict[str, object]) -> dict[str, tuple[str, ...]]:
        """Validate ``[tool.oo-ratchet.suggest]``: ring keys, each a name list."""
        where = "[tool.oo-ratchet.suggest]"
        found: dict[str, tuple[str, ...]] = {}
        for key, value in table.items():
            if key not in NameConvention.DEFAULTS:
                allowed = list(NameConvention.DEFAULTS)
                raise LayerConfigError(f"{where} unknown key {key!r}; use {allowed}")
            if not isinstance(value, list) or not all(
                isinstance(v, str) and v for v in value
            ):
                raise LayerConfigError(f"{where} {key} must be a list of package names")
            found[key] = tuple(value)
        return found

    def intent(self, module: str, package: str) -> Intent | None:
        """Return the ring the module's package names suggest, if any."""
        below = module.split(".")[1:] if module.startswith(package + ".") else []
        hits = {
            (ring, seg)
            for seg in below
            for ring, names in self._names.items()
            if seg in names
        }
        rings = {ring for ring, _ in hits}
        if len(rings) > 1:
            named = ", ".join(f"`{seg}` ({ring})" for ring, seg in sorted(hits))
            return Intent(None, f"ambiguous package names: {named}")
        if not hits:
            return None
        ring, seg = sorted(hits)[0]
        return Intent(ring, f"name convention: package `{seg}`")


class RingIntent:
    """Read a module's declared ring (marker, then layers table), then its name."""

    _table: LayerConfig | None
    _names: NameConvention

    def __new__(cls, table: LayerConfig | None, overrides: dict[str, object]) -> Self:
        self = super().__new__(cls)
        self._table = table
        self._names = NameConvention(overrides)
        return self

    def of(self, fact: ModuleFacts, package: str) -> Intent | None:
        """Return the module's intent: declaration first, then its name."""
        declared = self._declared(fact)
        if declared is not None:
            return declared
        return self._names.intent(fact.name, package)

    def _declared(self, fact: ModuleFacts) -> Intent | None:
        if fact.marker_problem:
            return Intent(None, fact.marker_problem)
        marker = self._marker(fact)
        tabled = self._table.layer(fact.name) if self._table else None
        if marker and marker.ring is None:
            return marker
        if marker and tabled and marker.ring != tabled:
            why = f"declarations disagree: __ring__ {marker.ring}, "
            return Intent(None, f"{why}[tool.oo-ratchet.layers] {tabled}")
        if marker:
            return marker
        return Intent(tabled, "[tool.oo-ratchet.layers]") if tabled else None

    @staticmethod
    def _marker(fact: ModuleFacts) -> Intent | None:
        if fact.marker is None:
            return None
        if fact.marker not in RINGS:
            named = ", ".join(RINGS)
            return Intent(None, f"__ring__ {fact.marker!r} is not one of {named}")
        return Intent(fact.marker, "__ring__ marker")
