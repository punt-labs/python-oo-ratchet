"""Find and read ``[tool.oo-ratchet.layers]``, choosing the fixed or declared form."""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Self

from .declared_layers import DeclaredLayers
from .layer_config import LayerConfig, LayerConfigError

if TYPE_CHECKING:
    from pathlib import Path


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
    def read(cls, anchor: Path, override: Path | None = None) -> Self:
        """Read an explicit file or the nearest ancestor pyproject, if any."""
        path = override or cls.nearest(anchor)
        if path is None:
            return cls({}, "no pyproject")
        return cls(cls._read(path), str(path), strict=override is not None)

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
        table = self._document
        for key in ("tool", "oo-ratchet", "layers"):
            if not isinstance(table, dict):
                raise LayerConfigError(
                    f"{self._label}: layer configuration must be a table"
                )
            if key not in table:
                if self._strict:
                    raise LayerConfigError(
                        f"{self._label}: missing [tool.oo-ratchet.layers]"
                    )
                return None
            table = table[key]
        if not isinstance(table, dict):
            raise LayerConfigError(f"{self._label}: layers must be a table")
        return self.build(table)

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
