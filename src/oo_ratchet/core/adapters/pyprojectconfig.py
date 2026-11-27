"""Read a gate's ``[tool.oo-ratchet.*]`` table from pyproject.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Self

from oo_ratchet.core.domain.errors import StateError


class PyprojectConfig:
    """The pyproject.toml of a project, read once, queried by table path."""

    _path: Path
    _data: dict[str, object]

    def __new__(cls, path: Path) -> Self:
        self = super().__new__(cls)
        self._path = path
        self._data = cls._load(path)
        return self

    def table(self, *keys: str) -> dict[str, object]:
        """Return the table at ``keys``; ``{}`` when it is genuinely absent.

        A key that exists with the wrong shape is corrupt data that would
        undercount, so it raises ``StateError`` instead.
        """
        node: object = self._data
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return {}
            node = node[key]
        if not isinstance(node, dict):
            raise StateError(f"[{'.'.join(keys)}] in {self._path} is not a table")
        return node

    @staticmethod
    def _load(path: Path) -> dict[str, object]:
        if not path.exists():
            return {}  # no pyproject.toml legitimately configures nothing
        try:
            return tomllib.loads(path.read_text())
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            raise StateError(f"cannot read {path}: {exc}") from exc
