"""Repo-named layers with prefix matching and an explicit allowed-imports table.

Each layer is a table with ``prefixes`` (relative to the scanned package) and
the layers it may ``imports``::

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

from typing import ClassVar, Self

from .layer_config import LayerConfig, LayerConfigError


class DeclaredLayers(LayerConfig):
    """A layer config whose layer names, prefixes and import rules are the repo's."""

    ORDERED: ClassVar[bool] = False
    EXEMPTS_ROOT: ClassVar[bool] = True
    _imports: dict[str, frozenset[str]]

    def __new__(cls, table: dict[str, object]) -> Self:
        self = object.__new__(cls)
        self._patterns, self._imports = cls._declared(table)
        return self

    def layer(self, module: str) -> str | None:
        """Return the layer with the longest matching prefix, if any."""
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

    def allowed(self, source: str) -> frozenset[str]:
        """Return ``source`` itself plus the layers it lists in ``imports``."""
        return self._imports[source] | {source}

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
            patterns[name] = cls._prefixes(name, spec.get("prefixes"))
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

    @classmethod
    def _prefixes(cls, name: str, value: object) -> list[str]:
        prefixes = cls._globs(value if value is not None else [])
        if not prefixes:
            raise LayerConfigError(f"layer {name!r} needs a non-empty prefixes list")
        for prefix in prefixes:
            if "*" in prefix.removesuffix("*") or prefix.endswith("."):
                raise LayerConfigError(
                    f"layer {name!r}: prefix {prefix!r} may only end in * and not in ."
                )
        return prefixes
