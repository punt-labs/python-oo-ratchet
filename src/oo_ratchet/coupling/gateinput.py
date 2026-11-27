"""What the shared gate core needs from a coupling scan: a policy and scores."""

from __future__ import annotations

from typing import Self

from oo_ratchet.core.application.pathtargets import PathTargets
from oo_ratchet.core.application.policy import GatePolicy
from oo_ratchet.core.domain.metrics import Metric
from oo_ratchet.core.domain.scores import Measurement, Score

from .config import CouplingConfig
from .scorer import CouplingScorer
from .thresholds import CouplingThresholds


class GateInput:
    """Translate a scored tree and its settings into the core's own types."""

    _config: CouplingConfig
    _scorer: CouplingScorer

    def __new__(cls, config: CouplingConfig, scorer: CouplingScorer) -> Self:
        self = super().__new__(cls)
        self._config = config
        self._scorer = scorer
        return self

    @property
    def measurement(self) -> Measurement:
        """Return the scored files and the unparseable ones."""
        names = CouplingThresholds.names()
        scores = tuple(
            Score(str(r["file"]), {k: float(r[k]) for k in names if k in r})
            for r in self._scorer.results
            if "error" not in r
        )
        return Measurement(scores, self._scorer.parse_errors)

    @property
    def policy(self) -> GatePolicy:
        """Return the coupling gate's policy.

        Regression-only, judged against the in-tree rows. ``__main__.py`` and
        each capped path are judged by their own targets.
        """
        table = CouplingThresholds.TABLE
        main = tuple(
            Metric(name, table[name][0], target)
            for name, (_, target) in CouplingThresholds.MAIN_TABLE.items()
        )
        return GatePolicy(
            tuple(Metric(name, op, target) for name, (op, target) in table.items()),
            must_improve=False,
            absolute_targets=False,
            lock_rows=False,
            in_tree_only=True,
            detailed_refusals=True,
            targets=PathTargets((("__main__.py", main),), self._capped()),
        )

    def _capped(self) -> dict[str, tuple[Metric, ...]]:
        """Return each configured path's caps as metrics; ``==`` caps as ``<=``."""
        table = CouplingThresholds.TABLE
        return {
            path: tuple(
                Metric(name, "<=" if table[name][0] == "==" else table[name][0], cap)
                for name, cap in caps.items()
            )
            for path, caps in self._config.caps.items()
        }
