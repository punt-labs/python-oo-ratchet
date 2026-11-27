"""A file's measured metrics and the baseline row that records them."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True, slots=True)
class Score:
    """One file's measured metrics, as a gate's scorer reports them."""

    path: str
    metrics: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class BaselineRow:
    """One file's recorded metrics, as a baseline stores them."""

    path: str
    metrics: Mapping[str, float]

    @classmethod
    def of(cls, score: Score) -> Self:
        """Return the row that records ``score``."""
        return cls(score.path, dict(score.metrics))


@dataclass(frozen=True, slots=True)
class Measurement:
    """Everything a scan of the tree found: scores and unparseable files."""

    scores: tuple[Score, ...]
    parse_errors: frozenset[str] = frozenset()

    @property
    def paths(self) -> frozenset[str]:
        """Return the scored (parse-clean) paths."""
        return frozenset(score.path for score in self.scores)

    def metrics(self) -> dict[str, dict[str, float]]:
        """Return the scores as path to metric values."""
        return {score.path: dict(score.metrics) for score in self.scores}
