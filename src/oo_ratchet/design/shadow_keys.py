"""Stable, unweighted design debt identities and tier differences."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import ClassVar, Self

from .findings import Rules


@dataclass(frozen=True, order=True, slots=True)
class DesignKey:
    """A finding identity, independent of line number and diagnostic detail."""

    rule: str
    module: str
    symbol: str


class KeyChanges:
    """Compare finding multiplicities without matching renamed modules."""

    TIER0: ClassVar[frozenset[str]] = frozenset(
        {Rules.SIZE_CAP, Rules.LAYER_IMPORT, Rules.DOMAIN_IO}
    )
    _added: tuple[DesignKey, ...]
    _removed: tuple[DesignKey, ...]

    def __new__(
        cls, base: tuple[DesignKey, ...], current: tuple[DesignKey, ...]
    ) -> Self:
        self = super().__new__(cls)
        before, after = Counter(base), Counter(current)
        self._added = tuple(sorted((after - before).elements()))
        self._removed = tuple(sorted((before - after).elements()))
        return self

    def added(self, tier: int) -> tuple[DesignKey, ...]:
        """Return added keys of the requested design tier."""
        return tuple(k for k in self._added if (k.rule in self.TIER0) == (tier == 0))

    def removed(self, tier: int) -> tuple[DesignKey, ...]:
        """Return removed keys of the requested design tier."""
        return tuple(k for k in self._removed if (k.rule in self.TIER0) == (tier == 0))

    def mapping(self, tier: int) -> dict[str, list[dict[str, str]]]:
        """Return sorted JSON-ready added and removed identities."""
        return {
            "added": [asdict(k) for k in self.added(tier)],
            "removed": [asdict(k) for k in self.removed(tier)],
        }
