"""Diagnostic lines for the ways a gate operation ends without succeeding.

A write that succeeds logs what it wrote, where the file is written. A
refusal or a failure is decided far from any file, so the views that turn a
verdict into an exit code log it here, once, in plain words: the reason kind
and how many subjects it names, never the subjects' content.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import ClassVar, Self

from oo_ratchet.core.domain.verdicts import Failure

logger = logging.getLogger(__name__)


class OutcomeLog:
    """Log a refused verdict or an unreadable state once, at the level that fits."""

    POLICY: ClassVar[frozenset[str]] = frozenset(
        {
            "regression",
            "no-improvement",
            "suppression-increase",
            "raise-refused",
            "missing-row",
            "stale-row",
            "refused",
            "nothing-to-relax",
            "not-scored",
            "no-row",
            "parse-refused",
            "new-violations",
            "stale-entries",
            "refuse-problems",
            "refuse-new",
        }
    )

    _failures: tuple[Failure, ...]

    def __new__(cls, failures: Iterable[Failure]) -> Self:
        self = super().__new__(cls)
        self._failures = tuple(failures)
        return self

    def refused(self) -> None:
        """Log why a verdict failed; nothing for a verdict that passed.

        A gate doing its job (a regression, a refused loosening) is INFO. A
        reason the caller must act on, such as an unresolvable base or a
        refused write under CI, is a WARNING.
        """
        if not self._failures:
            return
        kinds = ", ".join(f.kind for f in self._failures)
        subjects = sum(len(f.subjects) for f in self._failures)
        policy = all(f.kind in self.POLICY for f in self._failures)
        log = logger.info if policy else logger.warning
        log("Operation refused: %s (%d subjects)", kinds, subjects)

    @staticmethod
    def unreadable(exc: Exception) -> None:
        """Log that recorded state or configuration could not be used.

        The exception text is the tool's own sentence (a path and a parser
        position); the shared redactor masks home paths and URL credentials.
        It is logged escaped, with ``%r``, never raw.
        """
        logger.warning("Gate state unreadable (%s): %r", type(exc).__name__, str(exc))
