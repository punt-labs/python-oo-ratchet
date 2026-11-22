"""Git queries the layers ratchet needs, on top of the coupling gate's."""

from __future__ import annotations

from oo_ratchet.coupling.gitio import GitRepo

from .baseline import LayersBaseline


class LayersGit(GitRepo):
    """Resolve the comparison base and read the layers baseline committed at it."""

    def show_baseline_text(self, ref: str) -> str | None:
        """Return the baseline JSON committed at ``ref``, or ``None`` if absent."""
        return self._show_file(ref, LayersBaseline.FILENAME)

    def show_text(self, ref: str, path: str) -> str | None:
        """Return the repo-relative file ``path`` at ``ref``, or ``None`` if absent."""
        return self._show_file(ref, path)

    def exists_at(self, ref: str, path: str) -> bool:
        """Return whether the repo-relative file ``path`` exists at ``ref``."""
        return self._show_file(ref, path) is not None

    def has_package(self, name: str) -> bool:
        """Return whether a package directory ``name`` exists anywhere in the tree."""
        glob = f":(glob)**/{name}/__init__.py"
        found = self._git(
            ["ls-files", "--cached", "--others", "--exclude-standard", "--", glob]
        )
        return bool(found and found.strip())
