"""Find and read ``[tool.oo-ratchet.layers]``, choosing the fixed or declared form."""

from __future__ import annotations

import tomllib
from typing import Self

from .declared_layers import DeclaredLayers
from .layer_config import LayerConfig, LayerConfigError


class LayerTable:
    """One parsed pyproject and the layers table it may hold."""

    _document: object
    _label: str
    _strict: bool

    def __new__(cls, document: object, label: str, *, strict: bool = False) -> Self:
        self = super().__new__(cls)
        self._document = document
        self._label = label
        self._strict = strict
        return self

    @classmethod
    def from_text(cls, text: str, label: str) -> Self:
        """Read the pyproject ``text``, which may hold no layers table."""
        try:
            document: object = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise LayerConfigError(f"cannot read {label}: {exc}") from exc
        return cls(document, label)

    def config(self) -> LayerConfig | None:
        """Return the config the table describes; ``None`` when it has none."""
        table: object = self._document
        for key in ("tool", "oo-ratchet", "layers"):
            table = self._step(table, key)
            if table is None:
                return None
        if not isinstance(table, dict):
            raise LayerConfigError(f"{self._label}: layers must be a table")
        return self.build(table)

    def _step(self, table: object, key: str) -> object | None:
        if not isinstance(table, dict):
            raise LayerConfigError(
                f"{self._label}: layer configuration must be a table"
            )
        if key in table:
            found: object = table[key]
            return found
        if self._strict:
            raise LayerConfigError(f"{self._label}: missing [tool.oo-ratchet.layers]")
        return None

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
