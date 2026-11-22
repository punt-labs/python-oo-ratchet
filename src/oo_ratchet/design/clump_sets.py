"""Intersection closure and maximal repeated field-name sets."""

from __future__ import annotations

from typing import Self


class ClumpSets:
    """Retain maximal intersections for each identical set of supporting owners."""

    _sets: list[frozenset[str]]

    def __new__(cls, sets: list[frozenset[str]]) -> Self:
        self = super().__new__(cls)
        self._sets = sets
        return self

    def repeated(self) -> list[tuple[frozenset[str], tuple[int, ...]]]:
        """Return deterministic candidates of four names supported by three owners."""
        groups: dict[tuple[int, ...], list[frozenset[str]]] = {}
        for candidate in sorted(self._intersections(), key=lambda s: tuple(sorted(s))):
            owners = tuple(
                i for i, names in enumerate(self._sets) if candidate <= names
            )
            if len(owners) >= 3:
                groups.setdefault(owners, []).append(candidate)
        return [
            (names, owners)
            for owners, candidates in groups.items()
            for names in candidates
            if not any(names < other for other in candidates)
        ]

    def _intersections(self) -> set[frozenset[str]]:
        candidates: set[frozenset[str]] = set()
        for names in sorted(set(self._sets), key=lambda s: tuple(sorted(s))):
            intersections = {candidate & names for candidate in candidates}
            candidates.update(s for s in intersections | {names} if len(s) >= 4)
        return candidates
