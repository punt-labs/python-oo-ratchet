"""Read a file committed at a ref, on top of the coupling gate's git access."""

from __future__ import annotations

from oo_ratchet.coupling.gitio import GitRepo


class LayersGit(GitRepo):
    """Resolve the comparison base and read repository files committed at it."""

    def show_text(self, ref: str, path: str) -> str | None:
        """Return the repo-relative file ``path`` at ``ref``, or ``None`` if absent."""
        return self._show_file(ref, path)
