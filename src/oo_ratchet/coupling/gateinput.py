"""What the shared gate core needs from a coupling scan: a policy and scores."""

from __future__ import annotations

from typing import Self

from oo_ratchet.core.application.pathtargets import PathTargets
from oo_ratchet.core.application.policy import GatePolicy
from oo_ratchet.core.domain.scores import Measurement, Score

from .config import CouplingConfig
from .scorer import CouplingScorer
from .thresholds import COUPLING_METRICS, MAIN_METRICS, CouplingTargets


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
        names = COUPLING_METRICS.names
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
        return GatePolicy(
            COUPLING_METRICS.items,
            must_improve=False,
            absolute_targets=False,
            lock_rows=False,
            in_tree_only=True,
            detailed_refusals=True,
            targets=PathTargets(
                (("__main__.py", MAIN_METRICS.items),),
                CouplingTargets(self._config.caps).capped(),
            ),
        )
