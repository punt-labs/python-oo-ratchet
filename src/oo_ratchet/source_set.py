"""The source-selection facade used by gates, independent of physical layout."""

from __future__ import annotations

import argparse
import os.path
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Self

from .source_history import SourceHistory
from .source_options import SourceOptions
from .source_rescan import NamespaceRescan
from .sources import Sources

if TYPE_CHECKING:
    from oo_ratchet.core.application.ports import ArchiveRepo

type Source = Path | SourceSet


class SourceSet:
    """Resolve one legacy target or the physical portions of one namespace."""

    _target: Path | Sources

    def __new__(cls, target: Path | Sources | Self) -> Self:
        if isinstance(target, cls):
            return target
        self = super().__new__(cls)
        self._target = target._target if isinstance(target, SourceSet) else target
        return self

    @classmethod
    def from_roots(
        cls, roots: tuple[Path, ...], namespace: str, project: Path | None = None
    ) -> Self:
        """Resolve and validate namespace portions once at the caller boundary."""
        return cls(Sources(roots, namespace, project))

    @staticmethod
    def add(parser: argparse.ArgumentParser) -> None:
        """Add source-selection arguments without exposing their implementation."""
        SourceOptions.add(parser)

    @classmethod
    def parse(
        cls, parser: argparse.ArgumentParser, argv: list[str] | None
    ) -> argparse.Namespace:
        """Keep legacy Path options; pass a resolved namespace set down the pipeline."""
        options = SourceOptions.parse(parser, argv)
        if isinstance(options.src, Sources):
            options.src = cls(options.src)
        return options

    @staticmethod
    def path(target: Source) -> Path:
        """Return the physical anchor without changing legacy Path spelling."""
        return target.anchor if isinstance(target, SourceSet) else target

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
        return any((root / component).is_dir() for root in self.roots)

    def package_dirs(self) -> list[Path]:
        """Return non-root regular packages from the selected portions."""
        return [
            p.parent
            for p in self.files()
            if p.name == "__init__.py" and self.key_for(p) != "__init__"
        ]

    def inside(self, root: Path) -> bool:
        """Require every portion, not just their lexical anchor, inside the repo."""
        return all(path.resolve().is_relative_to(root.resolve()) for path in self.roots)

    def require_package(self, error: type[Exception]) -> None:
        """Require legacy initializers, but allow PEP 420 namespace portions."""
        if (
            isinstance(self._target, Path)
            and not (self._target / "__init__.py").is_file()
        ):
            raise error(
                f"{self._target} is not a package: no __init__.py (pass src/<package>)"
            )

    def at_base(self, repo: Path, tree: Path, renames: dict[str, str]) -> Source:
        """Select historical physical portions using the same resolved namespace."""
        if isinstance(self._target, Sources):
            return SourceSet(SourceHistory.at(self._target, repo, tree, renames))
        return tree / self._target.resolve().relative_to(repo)

    @staticmethod
    def remap_metrics(
        base: dict[str, dict[str, float]], renames: dict[str, str]
    ) -> dict[str, dict[str, float]]:
        """Pair current physical paths with renamed historical metrics."""
        return SourceHistory.metrics(base, renames)

    def shadow[T](
        self,
        layers: Path | None,
        ref: str,
        legacy: Callable[[Path, Path | None, str], T],
        namespace: Callable[[SourceSet, Path | None, str], T],
    ) -> T:
        """Choose a shadow scan strategy without exposing namespace dispatch."""
        return (
            namespace(self, layers, ref)
            if isinstance(self._target, Sources)
            else legacy(self._target, layers, ref)
        )

    def report_paths[T](
        self, report: T, root: Path, rebase: Callable[[T, str, str], T]
    ) -> T:
        """Normalize namespace report keys, leaving legacy report spelling intact."""
        return (
            rebase(report, str(root.resolve()) + "/", "")
            if isinstance(self._target, Sources)
            else report
        )

    def rescan[T](
        self,
        ref: str,
        git: ArchiveRepo,
        legacy: Callable[[str, Path], T | None],
        scan: Callable[[Source, Path], T],
        rebase: Callable[[T, str, str], T],
    ) -> T | None:
        """Materialize and scan the matching base source selection."""
        if isinstance(self._target, Path):
            return legacy(ref, self._target)
        pipeline = NamespaceRescan(
            git, lambda target, root: scan(SourceSet(target), root), rebase
        )
        return pipeline.scan(ref, self._target)

    def __str__(self) -> str:
        return str(self._target)
