"""Locate namespace portions in a historical tree through physical Git renames."""

from __future__ import annotations

from pathlib import Path

from .sources import Sources


class SourceHistory:
    """Translate source selections, not module identities, across a checkout."""

    @staticmethod
    def at(
        source: Sources, repo: Path, tree: Path, renames: dict[str, str]
    ) -> Path | Sources:
        """Select the same portions at the base, including moved namespace roots."""
        roots = {
            root
            for pattern in source.patterns or source.roots
            for root in tree.glob(str(pattern.relative_to(repo)))
            if root.is_dir()
        }
        for new, old in renames.items():
            if not any((repo / new).is_relative_to(root) for root in source.roots):
                continue
            root = SourceHistory._old_root(old, source, tree)
            if root is not None:
                roots.add(root)
        if not roots:
            return tree / source.roots[0].relative_to(repo)
        project = tree / source.project.relative_to(repo) if source.project else None
        return Sources(tuple(sorted(roots)), source.namespace, project)

    @staticmethod
    def _old_root(old: str, source: Sources, tree: Path) -> Path | None:
        parts = Path(old).parts
        if source.namespace not in parts:
            return None
        root = tree.joinpath(*parts[: parts.index(source.namespace) + 1])
        return root if root.is_dir() else None

    @staticmethod
    def metrics(
        base: dict[str, dict[str, float]], renames: dict[str, str]
    ) -> dict[str, dict[str, float]]:
        """Keep physical metric keys while pairing renamed files with their base."""
        destinations = {old: new for new, old in renames.items()}
        return {destinations.get(path, path): values for path, values in base.items()}
