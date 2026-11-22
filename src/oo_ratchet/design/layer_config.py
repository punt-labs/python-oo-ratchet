"""Strict, optional layer declarations for the advisory design scan."""

from __future__ import annotations

import tomllib
from fnmatch import fnmatchcase
from pathlib import Path
from typing import ClassVar, Self


class LayerConfigError(ValueError):
    """A layer configuration could not be read or validated."""


class LayerConfig:
    """Match dotted modules, with outer layers taking precedence on overlap."""

    ORDER: ClassVar[tuple[str, ...]] = ("entry", "adapters", "application", "domain")
    _patterns: dict[str, list[str]]

    def __new__(cls, table: dict[str, object]) -> Self:
        self = super().__new__(cls)
        unknown = set(table) - set(cls.ORDER)
        if unknown:
            raise LayerConfigError(f"unknown layer keys: {sorted(unknown)}")
        self._patterns = {key: cls._globs(table.get(key, [])) for key in cls.ORDER}
        return self

    def layer(self, module: str) -> str | None:
        """Return the first matching layer in outer-to-inner order."""
        return next(
            (
                key
                for key, globs in self._patterns.items()
                if any(fnmatchcase(module, glob) for glob in globs)
            ),
            None,
        )

    @classmethod
    def load(cls, root: Path, override: Path | None = None) -> Self | None:
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
        return cls(table)

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

    @staticmethod
    def _globs(value: object) -> list[str]:
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item for item in value
        ):
            raise LayerConfigError("each layer must be a list of nonempty module globs")
        return value
