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
            for pattern in SourceHistory.patterns(source, repo, renames)
            for root in tree.glob(pattern)
            if root.is_dir()
        }
        if not roots:
            return tree / source.roots[0].relative_to(repo)
        project = tree / source.project.relative_to(repo) if source.project else None
        return Sources(tuple(sorted(roots)), source.namespace, project)

    @staticmethod
    def patterns(source: Sources, repo: Path, renames: dict[str, str]) -> set[str]:
        """Return historical root patterns, including selected physical renames."""
        patterns = {str(p.relative_to(repo)) for p in source.patterns or source.roots}
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
