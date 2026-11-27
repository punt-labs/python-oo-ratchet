"""Find and read ``[tool.oo-ratchet.layers]``, choosing the fixed or declared form."""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

from .declared_layers import DeclaredLayers
from .layer_config import LayerConfig, LayerConfigError

if TYPE_CHECKING:
    from pathlib import Path


class LayerTable:
    """Read the layers table of a pyproject and build the config it describes."""

    @classmethod
    def load(cls, anchor: Path, override: Path | None = None) -> LayerConfig | None:
        """Read an explicit file or the nearest ancestor pyproject, if any."""
        path = override or cls.nearest(anchor)
        if path is None:
            return None
        return cls._config(cls._read(path), str(path), strict=override is not None)

    @classmethod
    def from_text(cls, text: str, label: str) -> LayerConfig | None:
        """Read the layers table of pyproject ``text``; ``None`` when it has none."""
        try:
            table: object = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise LayerConfigError(f"cannot read {label}: {exc}") from exc
        return cls._config(table, label, strict=False)

    @classmethod
    def _config(cls, table: object, path: str, *, strict: bool) -> LayerConfig | None:
        for key in ("tool", "oo-ratchet", "layers"):
            if not isinstance(table, dict):
                raise LayerConfigError(f"{path}: layer configuration must be a table")
            if key not in table:
                if strict:
                    raise LayerConfigError(f"{path}: missing [tool.oo-ratchet.layers]")
                return None
            table = table[key]
        if not isinstance(table, dict):
            raise LayerConfigError(f"{path}: layers must be a table")
        return cls.build(table)

    @staticmethod
    def ordered(config: LayerConfig | None) -> LayerConfig | None:
        """Return ``config`` in the fixed form; declared layers shape no data rules."""
        return config if config is not None and config.ORDERED else None

    @staticmethod
    def build(table: dict[str, object]) -> LayerConfig:
        """Return the declared form when any layer is a table, else the fixed form."""
        if any(isinstance(value, dict) for value in table.values()):
            return DeclaredLayers(table)
        return LayerConfig(table)

    @staticmethod
    def nearest(anchor: Path) -> Path | None:
        """Return the pyproject of ``anchor`` or its nearest ancestor, if any."""
        return next(
            (
                parent / "pyproject.toml"
                for parent in (anchor.resolve(), *anchor.resolve().parents)
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
