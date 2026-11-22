"""Git queries the layers ratchet needs, on top of the coupling gate's."""

from __future__ import annotations

from oo_ratchet.coupling.gitio import GitRepo

from .baseline import LayersBaseline


class LayersGit(GitRepo):
    """Resolve the comparison base and read the layers baseline committed at it."""

    def show_baseline_text(self, ref: str) -> str | None:
        """Return the baseline JSON committed at ``ref``, or ``None`` if absent."""
        return self._show_file(ref, LayersBaseline.FILENAME)

    def show_pyproject_text(self, ref: str) -> str | None:
        """Return the repository-root ``pyproject.toml`` at ``ref``, or ``None``."""
        return self._show_file(ref, "pyproject.toml")
