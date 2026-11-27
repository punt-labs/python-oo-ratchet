"""Locate namespace portions in a historical tree through physical Git renames."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from .source_set import Source, SourceSelection
from .sources import Sources


class SourceHistory:
    """Translate one source selection, not module identities, across a checkout."""

    _selection: SourceSelection

    def __new__(cls, source: Source) -> Self:
        self = super().__new__(cls)
        self._selection = SourceSelection(source)
        return self

    def at_base(self, repo: Path, tree: Path, renames: dict[str, str]) -> Source:
        """Select historical physical portions using the same resolved namespace."""
        target = self._selection.target
        if isinstance(target, Sources):
            return SourceSelection(self.at(target, repo, tree, renames))
        return tree / target.resolve().relative_to(repo)

    @staticmethod
    def at(
        source: Sources, repo: Path, tree: Path, renames: dict[str, str]
    ) -> Path | Sources:
        """Select the same portions at the base, including moved namespace roots."""
        roots = SourceHistory._roots(
            SourceHistory.patterns(source, repo, renames), tree
        )
        if not roots:
            return tree / source.roots[0].relative_to(repo)
        project = tree / source.project.relative_to(repo) if source.project else None
        return Sources(tuple(sorted(roots)), source.namespace, project)

    @staticmethod
    def _roots(patterns: set[str], tree: Path) -> set[Path]:
        roots = {
            SourceHistory._resolved(p, tree)
            for pattern in patterns
            for p in tree.glob(pattern)
        }
        return {p for p in roots if p.is_dir()}

    @staticmethod
    def _resolved(path: Path, tree: Path) -> Path:
        root = path.resolve()
        if not root.is_relative_to(tree.resolve()):
            raise ValueError(f"historical namespace root escapes checkout: {path}")
        return root

    @staticmethod
    def patterns(source: Sources, repo: Path, renames: dict[str, str]) -> set[str]:
        """Return historical root patterns, including selected physical renames."""
        patterns = {
            str(p.relative_to(repo).with_name(source.namespace))
            for p in source.patterns + source.roots
        }
        for new, old in renames.items():
            parts = Path(old).parts
            if source.namespace in parts and any(
                (repo / new).is_relative_to(root) for root in source.roots
            ):
                patterns.add(str(Path(*parts[: parts.index(source.namespace) + 1])))
        return patterns

    @staticmethod
    def metrics(
        base: dict[str, dict[str, float]], renames: dict[str, str]
    ) -> dict[str, dict[str, float]]:
        """Keep physical metric keys while pairing renamed files with their base."""
        destinations = {old: new for new, old in renames.items()}
        return {destinations.get(path, path): values for path, values in base.items()}
