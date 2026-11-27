"""Per-repository coupling settings read from ``[tool.oo-ratchet.coupling]``.

Two settings let an adopting repository say what the strict defaults cannot:

``caps`` maps an exact repository-relative path to per-metric absolute caps,
for a wiring hub whose job is to import many modules::

    [tool.oo-ratchet.coupling.caps]
    "src/pkg/facade.py" = { efferent_coupling = 20 }

``stateless-values`` picks which classes LCOM skips as stateless values:
``"dataclass"`` (default) skips only a ``@dataclass`` or ``__slots__ = ()``
marker that stores no instance state; ``"any"`` skips every class that stores
no private ``self._*`` state, whatever its shape.
"""

from __future__ import annotations

import posixpath
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from oo_ratchet.core.application.pathtargets import PathTargets
from oo_ratchet.core.application.policy import GatePolicy
from oo_ratchet.core.domain.metrics import Metric

from .thresholds import CouplingThresholds

STATELESS_MODES = frozenset({"dataclass", "any"})


class CouplingConfigError(Exception):
    """``[tool.oo-ratchet.coupling]`` is unreadable or malformed."""


@dataclass(frozen=True, slots=True)
class CouplingConfig:
    """Validated coupling settings for one repository."""

    caps: dict[str, dict[str, float]] = field(default_factory=dict)
    stateless_values: str = "dataclass"

    def policy(self) -> GatePolicy:
        """Return the gate policy these settings give the coupling gate.

        Regression-only, judged against the in-tree rows; ``__main__.py``
        and each capped path are judged by their own targets.
        """
        table = CouplingThresholds.TABLE
        main = tuple(
            Metric(name, table[name][0], target)
            for name, (_, target) in CouplingThresholds.MAIN_TABLE.items()
        )
        exact = {
            path: tuple(
                Metric(name, "<=" if table[name][0] == "==" else table[name][0], cap)
                for name, cap in caps.items()
            )
            for path, caps in self.caps.items()
        }
        return GatePolicy(
            tuple(Metric(name, op, target) for name, (op, target) in table.items()),
            must_improve=False,
            absolute_targets=False,
            lock_rows=False,
            in_tree_only=True,
            detailed_refusals=True,
            targets=PathTargets((("__main__.py", main),), exact),
        )

    @classmethod
    def load(cls, root: Path) -> Self:
        """Read ``root/pyproject.toml``; absent file or table means defaults."""
        path = root / "pyproject.toml"
        if not path.is_file():
            return cls()
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            msg = f"cannot read {path}: {exc}"
            raise CouplingConfigError(msg) from exc
        table: object = data
        for key in ("tool", "oo-ratchet", "coupling"):
            if not isinstance(table, dict):
                msg = f"{path}: [tool.oo-ratchet.coupling] path is not a table"
                raise CouplingConfigError(msg)
            table = table.get(key, {})
        if not isinstance(table, dict):
            msg = "[tool.oo-ratchet.coupling] must be a table"
            raise CouplingConfigError(msg)
        return cls.from_table(table)

    @classmethod
    def from_table(cls, table: dict[str, object]) -> Self:
        """Validate a parsed ``[tool.oo-ratchet.coupling]`` table."""
        unknown = set(table) - {"caps", "stateless-values"}
        if unknown:
            msg = f"unknown [tool.oo-ratchet.coupling] keys: {sorted(unknown)}"
            raise CouplingConfigError(msg)
        mode = table.get("stateless-values", "dataclass")
        if not isinstance(mode, str) or mode not in STATELESS_MODES:
            msg = f"stateless-values must be one of {sorted(STATELESS_MODES)}"
            raise CouplingConfigError(msg)
        return cls(caps=cls._parse_caps(table.get("caps", {})), stateless_values=mode)

    @staticmethod
    def _parse_caps(raw: object) -> dict[str, dict[str, float]]:
        if not isinstance(raw, dict):
            msg = "[tool.oo-ratchet.coupling.caps] must be a table"
            raise CouplingConfigError(msg)
        caps: dict[str, dict[str, float]] = {}
        for path, metrics in raw.items():
            if not isinstance(metrics, dict) or not metrics:
                msg = f"caps for {path!r} must be a non-empty table of metric caps"
                raise CouplingConfigError(msg)
            caps[CouplingConfig._normalize(path)] = {
                metric: CouplingConfig._cap_value(path, metric, value)
                for metric, value in metrics.items()
            }
        return caps

    @staticmethod
    def _cap_value(path: str, metric: str, value: object) -> float:
        if metric not in CouplingThresholds.TABLE:
            msg = f"caps for {path!r}: unknown metric {metric!r}"
            raise CouplingConfigError(msg)
        if isinstance(value, bool) or not isinstance(value, int | float):
            msg = f"caps for {path!r}: {metric} must be a number"
            raise CouplingConfigError(msg)
        return float(value)

    @staticmethod
    def _normalize(path: str) -> str:
        """Return ``path`` in the scorer's repo-relative POSIX key form."""
        norm = posixpath.normpath(path.replace("\\", "/")) if path else ""
        if not CouplingConfig._is_relative(norm):
            msg = f"caps path {path!r} must be repository-relative"
            raise CouplingConfigError(msg)
        return norm

    @staticmethod
    def _is_relative(norm: str) -> bool:
        """Return True for a normalized path inside the repository root."""
        if norm in ("", ".", "..") or norm.startswith(("/", "../")):
            return False
        return not (len(norm) > 1 and norm[1] == ":")
