"""Strict, optional layer declarations for the advisory design scan."""

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import ClassVar, Self


class LayerConfigError(ValueError):
    """A layer configuration could not be read or validated."""


class LayerConfig:
    """Match dotted modules, with outer layers taking precedence on overlap."""

    ORDER: ClassVar[tuple[str, ...]] = ("entry", "adapters", "application", "domain")
    ORDERED: ClassVar[bool] = True
    EXEMPTS_ROOT: ClassVar[bool] = False
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

    def allowed(self, source: str) -> frozenset[str]:
        """Return the layers ``source`` may import: itself and every inner one."""
        names = list(self._patterns)
        return frozenset(names[names.index(source) :])

    def layer_names(self) -> tuple[str, ...]:
        """Return the layers that name at least one pattern."""
        return tuple(name for name, globs in self._patterns.items() if globs)

    @staticmethod
    def _globs(value: object) -> list[str]:
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item for item in value
        ):
            raise LayerConfigError("each layer must be a list of nonempty module globs")
        return value
