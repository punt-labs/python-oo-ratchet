"""The source files an index of parsed modules is built from."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path


class ModuleSource(Protocol):
    """The source files of one package tree: what an index needs to know."""

    @property
    def name(self) -> str:
        """Return the spelling that pairs with a key to form a dotted import name."""
        ...

    @property
    def package_name(self) -> str:
        """Return the logical name of the scanned package."""
        ...

    def files(self) -> list[Path]:
        """Return each selected Python file once."""
        ...

    def key_for(self, path: Path) -> str:
        """Return the namespace-relative module key of ``path``."""
        ...

    def relative_path(self, path: Path) -> Path:
        """Return ``path`` relative to the source portion that owns it."""
        ...

    def read_source(self, path: Path) -> str:
        """Return the text of the Python file ``path``; ``OSError`` if unreadable."""
        ...

    def package_dirs(self) -> list[Path]:
        """Return the non-root package directories of the selection."""
        ...

    def contains(self, component: str) -> bool:
        """Return whether a source portion has the ``component`` directory."""
        ...
