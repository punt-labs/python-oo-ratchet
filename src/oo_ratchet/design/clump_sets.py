"""Pairwise candidates and maximal repeated field-name sets."""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Self


class ClumpSets:
    """Retain maximal intersections for each identical set of supporting owners."""

    _sets: list[frozenset[str]]
    _families: list[int]

    def __new__(
        cls, sets: list[frozenset[str]], families: list[int] | None = None
    ) -> Self:
        self = super().__new__(cls)
        self._sets = sets
        self._families = list(range(len(sets))) if families is None else families
        return self

    def repeated(self) -> list[tuple[frozenset[str], tuple[int, ...]]]:
        """Return deterministic candidates of four names supported by three owners."""
        groups: dict[tuple[int, ...], list[frozenset[str]]] = {}
        for candidate in sorted(self._intersections(), key=lambda s: tuple(sorted(s))):
            owners = tuple(
                sorted(
                    {
                        self._families[i]
                        for i, names in enumerate(self._sets)
                        if candidate <= names
                    }
                )
            )
            if len(owners) >= 3:
                groups.setdefault(owners, []).append(candidate)
        return [
            (names, self._representatives(names)) for names, _ in self._maximal(groups)
        ]

    def _representatives(self, candidate: frozenset[str]) -> tuple[int, ...]:
        representatives: dict[int, int] = {}
        for i, names in enumerate(self._sets):
            if candidate <= names:
                representatives.setdefault(self._families[i], i)
        return tuple(representatives.values())

    @staticmethod
    def _maximal(
        groups: dict[tuple[int, ...], list[frozenset[str]]],
    ) -> list[tuple[frozenset[str], tuple[int, ...]]]:
        return [
            (names, owners)
            for owners, candidates in groups.items()
            for names in candidates
            if not any(names < other for other in candidates)
        ]

    def _intersections(self) -> set[frozenset[str]]:
        owners = [names for names in self._supported_sets() if len(names) >= 4]
        return {
            candidate
            for left, right in combinations(owners, 2)
            if len(candidate := left & right) >= 4
        }

    def _supported_sets(self) -> list[frozenset[str]]:
        counts = Counter(
            name
            for _, name in {
                (family, name)
                for family, names in zip(self._families, self._sets, strict=True)
                for name in names
            }
        )
        return [
            frozenset(name for name in names if counts[name] >= 3)
            for names in self._sets
        ]
