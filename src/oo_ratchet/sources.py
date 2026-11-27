"""Physical portions of one import namespace, without a synthetic source tree."""

from __future__ import annotations

import keyword
import os.path
import tomllib
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
            if keys.setdefault(key, path) != path:
                raise ValueError(
                    f"duplicate module {self.namespace}.{key}: {keys[key]}, {path}"
                )
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

    @classmethod
    def select(cls, roots: list[str], namespace: str | None) -> Path | Sources:
        """Resolve command-line or configured roots to a legacy Path or Sources."""
        if len(roots) == 1 and namespace is None:
            return Path(roots[0])
        config, base = cls._config()
        selected = namespace if namespace is not None else config.get("namespace")
        if not roots:
            roots = cls._configured(config, base)
        if not roots:
            raise ValueError("the following arguments are required: src")
        if not isinstance(selected, str):
            raise ValueError("multiple roots need --namespace or configured namespace")
        paths = cls._paths(roots)
        return cls(
            tuple(sorted(paths)),
            selected,
            cls._project(base, paths),
            tuple(Path(root).resolve() for root in roots),
        )

    @staticmethod
    def _project(base: Path, paths: set[Path]) -> Path | None:
        if not (base / "pyproject.toml").is_file():
            return None
        return base if all(p.is_relative_to(base) for p in paths) else None

    @staticmethod
    def _configured(config: dict[str, object], base: Path) -> list[str]:
        configured = config.get("roots", [])
        if not isinstance(configured, list) or not all(
            isinstance(p, str) and p for p in configured
        ):
            raise ValueError("roots must be a list of nonempty path/glob strings")
        return [str(base / p) for p in configured]

    @staticmethod
    def _paths(roots: list[str]) -> set[Path]:
        paths: set[Path] = set()
        for pattern in roots:
            path = Path(pattern).absolute()
            matches = list(Path(path.anchor).glob(str(path.relative_to(path.anchor))))
            if not matches:
                raise ValueError(f"source root matches nothing: {pattern}")
            paths.update(p.resolve() for p in matches)
        return paths

    @staticmethod
    def _config() -> tuple[dict[str, object], Path]:
        for parent in (Path.cwd(), *Path.cwd().parents):
            if (file := parent / "pyproject.toml").is_file():
                table = tomllib.loads(file.read_text(encoding="utf-8"))
                tool = table.get("tool", {})
                if not isinstance(tool, dict):
                    raise ValueError("[tool] must be a table")
                config = tool.get("oo-ratchet", {})
                if not isinstance(config, dict):
                    raise ValueError("[tool.oo-ratchet] must be a table")
                return config, parent
            if (parent / ".git").exists():
                break
        return {}, Path.cwd()

    def __str__(self) -> str:
        return ", ".join(str(root) for root in self.roots)
