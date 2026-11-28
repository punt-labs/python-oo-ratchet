"""Project a scan into stable design identities and existing OO metrics."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Self

from oo_ratchet.core.domain.layer_config import LayerConfigError
from oo_ratchet.oo.scoring import Scoring
from oo_ratchet.source_set import Source, SourceSelection

from .scan import DesignScanner
from .shadow_keys import DesignKey


class ShadowScan:
    """Reject unreadable Python rather than mistake skipped debt for a trade."""

    _keys: tuple[DesignKey, ...]
    _metrics: dict[str, dict[str, float]]

    def __new__(
        cls,
        source: Source,
        repo: Path,
        layers: Path | None,
        *,
        score: Callable[[Source, Path], Scoring],
        package_name: str | None = None,
    ) -> Self:
        self = super().__new__(cls)
        scanner = cls._scan(source, repo, layers, package_name)
        report = scanner.report
        scorer = score(source, repo)
        cls._reject_broken(scanner, scorer, repo)
        self._keys = tuple(
            DesignKey(
                f.rule,
                cls._module(
                    scanner.module_key(Path(f.path)),
                    package_name or SourceSelection(source).name,
                ),
                f.symbol,
            )
            for f in report._findings
        )
        self._metrics = scorer.rows
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
    def _scan(
        source: Source, repo: Path, layers: Path | None, package_name: str | None
    ) -> DesignScanner:
        try:
            return DesignScanner(source, layers, package_name=package_name)
        except LayerConfigError as exc:
            raise LayerConfigError(str(exc).replace(str(repo), "<repo>")) from exc

    @staticmethod
    def _reject_broken(scanner: DesignScanner, scorer: Scoring, repo: Path) -> None:
        broken = sorted(
            {p.relative_to(repo).as_posix() for p in scanner.report._skipped}
            | scorer.parse_errors
        )
        if broken:
            raise ValueError(f"unreadable or unparseable Python: {', '.join(broken)}")

    @staticmethod
    def _module(key: str, package_name: str) -> str:
        if key.startswith("/"):
            return package_name + ":" + key[1:]
        return package_name + ("" if key == "__init__" else "." + key)
