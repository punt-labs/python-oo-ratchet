"""Project a scan into stable design identities and existing OO metrics."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from oo_ratchet.oo.baseline import Baseline
from oo_ratchet.oo.scorer import Scorer

from .layer_config import LayerConfigError
from .scanner import DesignScanner
from .shadow_keys import DesignKey


class ShadowScan:
    """Reject unreadable Python rather than mistake skipped debt for a trade."""

    _keys: tuple[DesignKey, ...]
    _metrics: dict[str, dict[str, float]]

    def __new__(cls, source: Path, repo: Path, layers: Path | None) -> Self:
        self = super().__new__(cls)
        try:
            scanner = DesignScanner(source, layers)
            report = scanner.report
        except LayerConfigError as exc:
            raise LayerConfigError(str(exc).replace(str(repo), "<repo>")) from exc
        scorer = Scorer(source, repo)
        broken = sorted(
            {p.relative_to(repo).as_posix() for p in report._skipped}
            | scorer.parse_errors
        )
        if broken:
            raise ValueError(f"unreadable or unparseable Python: {', '.join(broken)}")
        self._keys = tuple(
            DesignKey(
                f.rule, cls._module(scanner.module_key(Path(f.path)), source), f.symbol
            )
            for f in report._findings
        )
        self._metrics = Baseline.metrics_by_file(scorer.results)
        return self

    @property
    def keys(self) -> tuple[DesignKey, ...]:
        """Return line-independent identities, preserving finding multiplicity."""
        return self._keys

    @property
    def metrics(self) -> dict[str, dict[str, float]]:
        """Return the OO scorer's per-file projection."""
        return self._metrics

    @staticmethod
    def _module(key: str, source: Path) -> str:
        if key.startswith("/"):
            return source.name + ":" + key[1:]
        return source.name + ("" if key == "__init__" else "." + key)
