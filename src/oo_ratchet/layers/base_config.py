"""The layer config as it was at the merge base."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from oo_ratchet.design.layer_config import LayerConfig, LayerConfigError
from oo_ratchet.design.layer_table import LayerTable

from .gitio import LayersGit
from .scan import LayerScan


class BaseConfig:
    """Read the layer config a scan used from the base commit."""

    _root: Path
    _git: LayersGit

    def __new__(cls, root: Path, git: LayersGit) -> Self:
        self = super().__new__(cls)
        self._root = root
        self._git = git
        return self

    def read(self, scan: LayerScan, base: str, *, strict: bool) -> LayerConfig | None:
        """Return the config at ``base`` from the pyproject the scan used.

        With ``strict`` a base that has no layer config there cannot be compared
        and the check fails; without it (a package new in this change) there is
        nothing to compare and ``None`` is returned. A config outside the
        repository always fails.
        """
        if scan.config_path is None:
            return None
        try:
            rel = scan.config_path.resolve().relative_to(self._root.resolve())
        except ValueError as exc:
            msg = f"layer config {scan.config_path} is outside {self._root}"
            raise LayerConfigError(msg) from exc
        path = rel.as_posix()
        text = self._git.show_text(base, path)
        config = LayerTable.from_text(text, f"{base}:{path}") if text else None
        if config is None and strict:
            where = f"{base[:10]}:{path}"
            msg = f"no layer config at the base ({where}) but a baseline exists"
            raise LayerConfigError(msg)
        return config
