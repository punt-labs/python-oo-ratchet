"""Scan one package with the design gate's layer rules, for the layers gate."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from oo_ratchet.design.layer_config import LayerConfig, LayerConfigError
from oo_ratchet.design.layer_edges import Edge, Violation
from oo_ratchet.design.layer_table import LayerTable
from oo_ratchet.design.modules import ModuleIndex

from .strict import StrictViolations


class LayersScanError(Exception):
    """The scanned directory is not a readable package with modules to check."""


class LayerScan:
    """The violating import edges of one package under a layer config.

    ``src`` is the package directory itself (``src/pkg``) and must hold an
    ``__init__.py`` and at least one module besides it. The config is read from
    the nearest ``pyproject.toml`` above it unless one is passed in; a missing
    ``[tool.oo-ratchet.layers]`` table is an error because the gate has nothing
    to enforce. Classification and import resolution are the design gate's, plus
    re-exports and literal dynamic imports. Like the design gate, imports under
    ``TYPE_CHECKING`` count as edges. A module the scan could not parse fails
    the scan instead of silently dropping its edges.

    ``problems`` lists what stops the scan vouching for the package: a module no
    layer claims, or a layer that claims no module.
    """

    _src: Path
    _config: LayerConfig
    _modules: tuple[str, ...]
    _violations: tuple[Violation, ...]
    _unassigned: tuple[str, ...]
    _unresolvable: tuple[str, ...]
    _config_path: Path | None
    _package: str

    def __new__(cls, src: Path, config: LayerConfig | None = None) -> Self:
        self = super().__new__(cls)
        self._src = src
        self._config = config or cls._load(src)
        if not (src / "__init__.py").is_file():
            msg = f"{src} is not a package: no __init__.py (pass src/<package>)"
            raise LayersScanError(msg)
        index = ModuleIndex(src)
        if index.skipped:
            names = ", ".join(sorted(str(p) for p in index.skipped))
            msg = f"cannot read or parse: {names}"
            raise LayersScanError(msg)
        found = StrictViolations(index, self._config)
        self._modules = tuple(sorted(found.name(m) for m in index.modules()))
        if all("." not in m for m in self._modules):
            msg = f"no modules to check under {src}"
            raise LayersScanError(msg)
        self._violations = tuple(found.violations())
        self._unassigned = tuple(found.unassigned())
        self._unresolvable = tuple(found.unresolvable())
        self._config_path = LayerTable.nearest(src)
        self._package = index.package_name
        return self

    def under(self, config: LayerConfig) -> Self:
        """Return the same package scanned under another layer config."""
        return type(self)(self._src, config)

    @property
    def modules(self) -> tuple[str, ...]:
        """Return the scanned module names, sorted."""
        return self._modules

    @property
    def violations(self) -> tuple[Violation, ...]:
        """Return the edges whose source layer may not import the target layer."""
        return self._violations

    @property
    def edges(self) -> frozenset[Edge]:
        """Return the violating edges."""
        return frozenset(v.edge for v in self._violations)

    @property
    def unassigned(self) -> tuple[str, ...]:
        """Return the non-root modules that match no layer."""
        return self._unassigned

    @property
    def src(self) -> Path:
        """Return the scanned package directory."""
        return self._src

    @property
    def package(self) -> str:
        """Return the scanned package's name, the prefix of its module names."""
        return self._package

    @property
    def config(self) -> LayerConfig:
        """Return the layer config the scan ran under."""
        return self._config

    @property
    def config_path(self) -> Path | None:
        """Return the pyproject the scan's config was read from, if one was found."""
        return self._config_path

    @property
    def problems(self) -> tuple[str, ...]:
        """Return why this scan cannot vouch for the package, if it cannot."""
        used = {self._config.layer(m) for m in self._modules}
        return (
            *(f"unassigned module: {m}" for m in self._unassigned),
            *(f"unresolvable relative import: {at}" for at in self._unresolvable),
            *(
                f"layer {name!r} matches no module"
                for name in self._config.layer_names()
                if name not in used
            ),
        )

    @staticmethod
    def _load(src: Path) -> LayerConfig:
        config = LayerTable.load(src)
        if config is None:
            msg = f"no [tool.oo-ratchet.layers] table above {src}"
            raise LayerConfigError(msg)
        return config
