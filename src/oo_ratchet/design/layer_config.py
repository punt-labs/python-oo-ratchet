"""Strict, optional layer declarations for the design scan and the layers gate.

Two spellings share the ``[tool.oo-ratchet.layers]`` table and may not be mixed.

The ordered form names the four fixed layers, each a list of module globs; a
layer may import itself and the layers after it in ``entry, adapters,
application, domain``::

    [tool.oo-ratchet.layers]
    entry = ["pkg.cli"]
    domain = ["pkg.model.*"]

The declared form names any layers, each a table with name ``prefixes``
(relative to the scanned package) and the layers it may ``imports``::

    [tool.oo-ratchet.layers.kernel]
    prefixes = ["paths", "log_*"]
    imports = []

    [tool.oo-ratchet.layers.service]
    prefixes = ["service", "hooks"]
    imports = ["kernel"]

A prefix ``"hooks"`` matches ``pkg.hooks`` and everything under it; a trailing
``*`` makes it a plain string prefix. The longest prefix wins and an exact
prefix beats a ``*`` prefix of equal length. The package root is exempt.
"""

from __future__ import annotations

import tomllib
from fnmatch import fnmatchcase
from pathlib import Path
from typing import ClassVar, Self


class LayerConfigError(ValueError):
    """A layer configuration could not be read or validated."""


class LayerConfig:
    """Classify dotted modules into layers and say which layers may import."""

    ORDER: ClassVar[tuple[str, ...]] = ("entry", "adapters", "application", "domain")
    _patterns: dict[str, list[str]]
    _imports: dict[str, frozenset[str]] | None

    def __new__(cls, table: dict[str, object]) -> Self:
        self = super().__new__(cls)
        if any(isinstance(value, dict) for value in table.values()):
            self._patterns, self._imports = cls._declared(table)
            return self
        unknown = set(table) - set(cls.ORDER)
        if unknown:
            raise LayerConfigError(f"unknown layer keys: {sorted(unknown)}")
        self._patterns = {key: cls._globs(table.get(key, [])) for key in cls.ORDER}
        self._imports = None
        return self

    @property
    def is_ordered(self) -> bool:
        """Return whether this is the fixed four-layer form."""
        return self._imports is None

    def layer(self, module: str) -> str | None:
        """Return the layer of a dotted module, or ``None`` when it has none."""
        if self._imports is not None:
            return self._by_prefix(module)
        return next(
            (
                key
                for key, globs in self._patterns.items()
                if any(fnmatchcase(module, glob) for glob in globs)
            ),
            None,
        )

    def exempts(self, module: str) -> bool:
        """Return whether a layerless module is exempt (declared form root)."""
        return self._imports is not None and "." not in module

    def permits(self, source: str, target: str) -> bool:
        """Return whether layer ``source`` may import layer ``target``."""
        if source == target:
            return True
        if self._imports is None:
            return self.ORDER.index(target) >= self.ORDER.index(source)
        return target in self._imports[source]

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

    def _by_prefix(self, module: str) -> str | None:
        if "." not in module:
            return None
        relative = module.split(".", 1)[1]
        ranked = [
            (*rank, layer)
            for layer, prefixes in self._patterns.items()
            for prefix in prefixes
            if (rank := self._match(prefix, relative)) is not None
        ]
        return max(ranked)[2] if ranked else None

    @staticmethod
    def _match(prefix: str, relative: str) -> tuple[int, bool] | None:
        """Return ``(length, is_exact)`` when ``prefix`` matches, else ``None``."""
        if prefix.endswith("*"):
            stem = prefix[:-1]
            return (len(stem), False) if relative.startswith(stem) else None
        if relative == prefix or relative.startswith(prefix + "."):
            return (len(prefix), True)
        return None

    @classmethod
    def _declared(
        cls, table: dict[str, object]
    ) -> tuple[dict[str, list[str]], dict[str, frozenset[str]]]:
        patterns: dict[str, list[str]] = {}
        imports: dict[str, frozenset[str]] = {}
        owner: dict[str, str] = {}
        for name, spec in table.items():
            if not isinstance(spec, dict) or set(spec) - {"prefixes", "imports"}:
                raise LayerConfigError(
                    f"layer {name!r} must be a table of prefixes and imports"
                )
            patterns[name] = cls._globs(spec.get("prefixes", []))
            for prefix in patterns[name]:
                other = owner.setdefault(prefix, name)
                if other != name:
                    raise LayerConfigError(
                        f"prefix {prefix!r} is in both {other!r} and {name!r}"
                    )
            imports[name] = frozenset(cls._globs(spec.get("imports", [])))
        for name, targets in imports.items():
            if not targets <= set(table):
                raise LayerConfigError(f"layer {name!r} imports an undeclared layer")
        return patterns, imports

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
