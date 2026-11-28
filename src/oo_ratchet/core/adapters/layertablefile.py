"""Find and read the pyproject.toml that holds ``[tool.oo-ratchet.layers]``."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from oo_ratchet.core.domain.layer_config import LayerConfigError
from oo_ratchet.core.domain.layer_table import LayerTable


@dataclass(frozen=True)
class LayerRead:
    """A layers table and the pyproject it came from (``None`` when there is none)."""

    table: LayerTable
    path: Path | None


class LayerTableFile:
    """The file-system side of ``LayerTable``: locate and read a pyproject."""

    @staticmethod
    def nearest(anchor: Path) -> Path | None:
        """Return the pyproject of ``anchor`` or its nearest ancestor, if any."""
        return next(
            (
                parent / "pyproject.toml"
                for parent in (anchor.resolve(), *anchor.resolve().parents)
                if (parent / "pyproject.toml").is_file()
            ),
            None,
        )

    @classmethod
    def read(cls, anchor: Path, override: Path | None = None) -> LayerRead:
        """Read an explicit file or the nearest ancestor pyproject, if any."""
        path = override or cls.nearest(anchor)
        if path is None:
            return LayerRead(LayerTable({}, "no pyproject"), None)
        table = LayerTable(cls._read(path), str(path), strict=override is not None)
        return LayerRead(table, path)

    @staticmethod
    def _read(path: Path) -> object:
        try:
            return tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise LayerConfigError(f"cannot read {path}: {exc}") from exc
