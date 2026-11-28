"""Count suppression comments over source text that has already been read."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from .patterns import FileSuppressions

if TYPE_CHECKING:
    from collections.abc import Mapping


class SuppressionCensus:
    """Count the suppressions of each named source text, in the order given."""

    _files: list[FileSuppressions]

    def __new__(cls, texts: Mapping[str, str]) -> Self:
        self = super().__new__(cls)
        self._files = [FileSuppressions(name, text) for name, text in texts.items()]
        return self

    @property
    def files(self) -> list[FileSuppressions]:
        """Return the per-file counts, one per text."""
        return list(self._files)
