"""Find and read ``[tool.oo-ratchet.layers]``, choosing the fixed or declared form."""

from __future__ import annotations

import tomllib
from pathlib import Path

from .declared_layers import DeclaredLayers
from .layer_config import LayerConfig, LayerConfigError


class LayerTable:
    """Read the layers table of a pyproject and build the config it describes."""

    @classmethod
    def load(cls, root: Path, override: Path | None = None) -> LayerConfig | None:
        """Read an explicit file or the nearest ancestor pyproject, if any."""
        path = override or cls._nearest(root)
        if path is None:
            return None
        table = cls._read(path)
        for key in ("tool", "oo-ratchet", "layers"):
            if not isinstance(table, dict):
                raise LayerConfigError(f"{path}: layer configuration must be a table")
            if key not in table:
                if override is not None:
                    raise LayerConfigError(f"{path}: missing [tool.oo-ratchet.layers]")
                return None
            table = table[key]
        if not isinstance(table, dict):
            raise LayerConfigError(f"{path}: layers must be a table")
        return cls.build(table)

    @staticmethod
    def build(table: dict[str, object]) -> LayerConfig:
        """Return the declared form when any layer is a table, else the fixed form."""
        if any(isinstance(value, dict) for value in table.values()):
            return DeclaredLayers(table)
        return LayerConfig(table)

    @staticmethod
    def _nearest(root: Path) -> Path | None:
        return next(
            (
                parent / "pyproject.toml"
                for parent in (root.resolve(), *root.resolve().parents)
                if (parent / "pyproject.toml").is_file()
            ),
            None,
        )

    @staticmethod
    def _read(path: Path) -> object:
        try:
            return tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise LayerConfigError(f"cannot read {path}: {exc}") from exc
