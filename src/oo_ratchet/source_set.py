"""The set of source files a gate reads, independent of physical layout.

The module keeps its name: the layers baseline holds its import edges by module.
"""

from __future__ import annotations

import os.path
from collections.abc import Callable
from pathlib import Path
from typing import Self

from oo_ratchet.core.domain.layer_table import LayerTable

from .core.adapters.layertablefile import LayerTableFile
from .sources import Sources

type Source = Path | SourceSelection


class SourceSelection:
    """Resolve one legacy target or the physical portions of one namespace."""

    _target: Path | Sources

    def __new__(cls, target: Path | Sources | Self) -> Self:
        if isinstance(target, cls):
            return target
        self = super().__new__(cls)
        self._target = target._target if isinstance(target, SourceSelection) else target
        return self

    @classmethod
    def from_roots(
        cls, roots: tuple[Path, ...], namespace: str, project: Path | None = None
    ) -> Self:
        """Resolve and validate namespace portions once at the caller boundary."""
        return cls(Sources(roots, namespace, project))

    @staticmethod
    def path(target: Source) -> Path:
        """Return the physical anchor without changing legacy Path spelling."""
        return target.anchor if isinstance(target, SourceSelection) else target

    def select[T](
        self, legacy: Callable[[Path], T], namespace: Callable[[Sources], T]
    ) -> T:
        """Apply ``legacy`` to a lone path or ``namespace`` to its portions."""
        target = self._target
        return namespace(target) if isinstance(target, Sources) else legacy(target)

    def layer_table(self, override: Path | None = None) -> LayerTable:
        """Read ``override`` or the nearest pyproject above the config anchor."""
        return LayerTableFile.read(self.config_anchor, override)

    def layer_config_path(self) -> Path | None:
        """Return the nearest pyproject above the config anchor, if any."""
        return LayerTableFile.nearest(self.config_anchor)

    @property
    def target(self) -> Path | Sources:
        """Return the legacy path or the namespace portions, as selected."""
        return self._target

    @property
    def anchor(self) -> Path:
        """Return the common physical ancestor of the selection."""
        return Sources.path(self._target)

    @property
    def roots(self) -> tuple[Path, ...]:
        """Return the real portions, never a merged or synthetic source tree."""
        return Sources.portions(self._target)

    @property
    def namespace(self) -> str | None:
        """Return the explicit namespace, absent in legacy mode."""
        return self._target.namespace if isinstance(self._target, Sources) else None

    @property
    def project(self) -> Path | None:
        """Return the configured project anchor when supplied."""
        return self._target.project if isinstance(self._target, Sources) else None

    @property
    def config_anchor(self) -> Path:
        """Return where ancestor configuration discovery starts."""
        return self.project or self.anchor

    @property
    def name(self) -> str:
        """Return the package spelling used by coupling import resolution."""
        return self.namespace or self.anchor.name

    @property
    def package_name(self) -> str:
        """Return the logical design name, preserving legacy symlink spelling."""
        return self.namespace or Path(os.path.normpath(self.anchor.absolute())).name

    @property
    def file(self) -> Path | None:
        """Return a legacy single-file target, never a namespace directory."""
        return (
            self._target
            if isinstance(self._target, Path) and self._target.is_file()
            else None
        )

    @property
    def start_dir(self) -> Path | None:
        """Return a directory suitable for Git discovery, if one exists."""
        return self.anchor if self.anchor.is_dir() else None

    def files(self) -> list[Path]:
        """Return each selected Python file once in stable physical-path order."""
        return Sources.files(self._target)

    def relative_path(self, path: Path) -> Path:
        """Return a path relative to its owning source portion."""
        root = (
            self._target.owner(path)
            if isinstance(self._target, Sources)
            else self.anchor
        )
        return path.relative_to(root)

    def key_for(self, path: Path) -> str:
        """Return the stable namespace-relative module identity."""
        return self.parts_to_key(self.relative_path(path).with_suffix("").parts)

    @staticmethod
    def parts_to_key(parts: tuple[str, ...]) -> str:
        """Retain the original initializer and dotted-key naming rules."""
        if len(parts) == 1:
            return parts[0]
        return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)

    def contains(self, component: str) -> bool:
        """Return whether any selected portion owns this component directory."""
        return any(
            (root / component).is_dir() for root in Sources.portions(self._target)
        )

    @staticmethod
    def read_source(path: Path) -> str:
        """Return the UTF-8 text of the Python file ``path``."""
        return path.read_text(encoding="utf-8")

    def package_dirs(self) -> list[Path]:
        """Return non-root regular packages from the selected portions."""
        return [
            p.parent
            for p in self.files()
            if p.name == "__init__.py" and self.key_for(p) != "__init__"
        ]

    def inside(self, root: Path) -> bool:
        """Require every portion, not just their lexical anchor, inside the repo."""
        repo = root.resolve()
        return all(
            path.resolve().is_relative_to(repo)
            for path in Sources.portions(self._target)
        )

    def require_package(self, error: type[Exception]) -> None:
        """Require legacy initializers, but allow PEP 420 namespace portions."""
        if (
            isinstance(self._target, Path)
            and not (self._target / "__init__.py").is_file()
        ):
            raise error(
                f"{self._target} is not a package: no __init__.py (pass src/<package>)"
            )

    def __str__(self) -> str:
        return str(self._target)
