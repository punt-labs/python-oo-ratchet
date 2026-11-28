"""One design request: a plain scan or a shadow comparison, optionally enforced."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Self

from oo_ratchet.core.domain.findings import Rules
from oo_ratchet.design.scanner import DesignScanner
from oo_ratchet.design.shadow import ShadowCheck
from oo_ratchet.source_set import Source

logger = logging.getLogger(__name__)


class DesignRun:
    """Scan once, render the report, and name the findings ``--enforce`` blocks.

    A plain scan blocks nothing. A shadow comparison blocks on each added key of
    a gate-capable rule, read from the documented JSON ``tier0`` and ``tier1``
    ``added`` lists.
    """

    _text: str
    _json: str
    _blocking: list[str]

    def __new__(
        cls, source: Source, layers: Path | None, ref: str | None, *, enforce: bool
    ) -> Self:
        if enforce and ref is None:
            msg = "--enforce needs --shadow-check"
            raise ValueError(msg)
        self = super().__new__(cls)
        report = (
            DesignScanner(source, layers).report
            if ref is None
            else ShadowCheck(source, layers, ref).report
        )
        self._text = report.to_text()
        self._json = report.to_json()
        self._blocking = cls._added(self._json) if enforce else []
        return self

    @staticmethod
    def _added(document: str) -> list[str]:
        tiers = json.loads(document)
        keys = [k for tier in ("tier0", "tier1") for k in tiers[tier]["added"]]
        return [
            f"({k['rule']}, {k['module']}, {k['symbol']})"
            for k in keys
            if k["rule"] in Rules.GATE_CAPABLE
        ]

    def render(self, *, as_json: bool) -> str:
        """Return the report in the requested format."""
        return self._json + "\n" if as_json else self._text

    def status(self) -> int:
        """Return 1 and name the blocking keys on stderr, else 0."""
        if not self._blocking:
            return 0
        logger.info(
            "Design findings enforced: %d added gate-capable", len(self._blocking)
        )
        sys.stderr.write(
            f"oo-ratchet design: --enforce: {len(self._blocking)} added "
            f"gate-capable finding(s): {', '.join(self._blocking)}\n"
        )
        return 1
