"""Physical portions of one import namespace, without a synthetic source tree."""

from __future__ import annotations

import keyword
import os.path
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Sources:
    """Join namespace directories while retaining their real file paths."""

    roots: tuple[Path, ...]
    namespace: str
    project: Path | None = None
    patterns: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        if not self.namespace.isidentifier() or keyword.iskeyword(self.namespace):
            raise ValueError("namespace must be a top-level Python identifier")
        if not self.roots:
            raise ValueError("namespace scan needs at least one root")
        for root in self.roots:
            if not root.is_dir() or root.name != self.namespace:
                raise ValueError(f"{root}: expected a directory named {self.namespace}")
        self._validate_modules()

    def _validate_modules(self) -> None:
        keys: dict[str, Path] = {}
        for path in self.files(self):
            key = self.key_for(path)
            if key in keys and keys[key] != path:
                raise ValueError(
                    f"duplicate module {self.namespace}.{key}: {keys[key]}, {path}"
                )
            keys[key] = path
        if not keys:
            raise ValueError("namespace roots contain no Python modules")

    @property
    def anchor(self) -> Path:
        """Return the common ancestor used to find project configuration."""
        return Path(os.path.commonpath([p.absolute() for p in self.roots]))

    def owner(self, path: Path) -> Path:
        """Return the namespace portion containing a physical file."""
        return next(root for root in self.roots if path.is_relative_to(root))

    def key_for(self, path: Path) -> str:
        """Return a namespace-relative key, as in the legacy package layout."""
        parts = path.relative_to(self.owner(path)).with_suffix("").parts
        return ".".join(
            parts[:-1] if len(parts) > 1 and parts[-1] == "__init__" else parts
        )

    @staticmethod
    def path(target: Path | Sources) -> Path:
        """Return the physical scan anchor, leaving legacy targets unchanged."""
        return target.anchor if isinstance(target, Sources) else target

    @staticmethod
    def portions(target: Path | Sources) -> tuple[Path, ...]:
        """Return all physical roots, including a legacy single-file target."""
        return target.roots if isinstance(target, Sources) else (target,)

    @staticmethod
    def files(target: Path | Sources) -> list[Path]:
        """Enumerate each Python file once, retaining legacy discovery rules."""
        files: set[Path] = set()
        for root in Sources.portions(target):
            if root.is_file():
                files.add(root)
            elif root.is_dir():
                files.update(
                    p for p in root.rglob("*.py") if not p.name.startswith(".")
                )
        return sorted(files)

    def __str__(self) -> str:
        return ", ".join(str(root) for root in self.roots)
