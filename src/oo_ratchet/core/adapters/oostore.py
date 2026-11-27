"""The OO gate's in-tree baseline file."""

from __future__ import annotations

from oo_ratchet.core.domain.errors import StateError
from oo_ratchet.core.domain.scores import Rows

from .formats import BaselineFormat
from .jsonstore import JsonBaselineStore


class OoBaselineStore(JsonBaselineStore):
    """The baseline file, whose errors name the file as ``baseline file <path>``."""

    def rows(self) -> Rows:
        """Return the recorded rows, ``{}`` when there is no file."""
        if not self.path.exists():
            return {}
        try:
            text = self.path.read_text()
        except (OSError, UnicodeDecodeError) as exc:
            raise StateError(f"unreadable baseline file {self.path}: {exc}") from exc
        return BaselineFormat.decode(text, f"file {self.path}")
