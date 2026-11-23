"""Shared opt-in namespace arguments and pyproject source selection."""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

from .sources import Sources


class SourceOptions:
    """Resolve explicit roots or configured globs before any gate writes files."""

    @staticmethod
    def add(parser: argparse.ArgumentParser) -> None:
        """Add the source arguments shared by every gate."""
        parser.add_argument(
            "src", nargs="*", help="package directory or namespace portions"
        )
        parser.add_argument(
            "--namespace", help="join roots of this top-level namespace"
        )

    @classmethod
    def parse(
        cls, parser: argparse.ArgumentParser, argv: list[str] | None
    ) -> argparse.Namespace:
        """Return options with a legacy Path or validated namespace sources."""
        ns = parser.parse_args(argv)
        try:
            ns.src = cls._target(ns.src, ns.namespace)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        return ns

    @classmethod
    def _target(cls, roots: list[str], namespace: str | None) -> Path | Sources:
        if len(roots) == 1 and namespace is None:
            return Path(roots[0])
        config, base = cls._config()
        selected = namespace if namespace is not None else config.get("namespace")
        if not roots:
            roots = cls._configured(config, base)
        if not roots:
            raise ValueError("the following arguments are required: src")
        if not isinstance(selected, str) or not selected:
            raise ValueError(
                "multiple roots require --namespace or configured namespace"
            )
        paths = cls._paths(roots)
        return Sources(
            tuple(sorted(paths)),
            selected,
            cls._project(base, paths),
            tuple(Path(root).absolute() for root in roots),
        )

    @staticmethod
    def _project(base: Path, paths: set[Path]) -> Path | None:
        return (
            base
            if (base / "pyproject.toml").is_file()
            and all(p.is_relative_to(base) for p in paths)
            else None
        )

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
            paths.update(p.absolute() for p in matches)
        return paths

    @staticmethod
    def _config() -> tuple[dict[str, object], Path]:
        for parent in (Path.cwd(), *Path.cwd().parents):
            file = parent / "pyproject.toml"
            if file.is_file():
                table = tomllib.loads(file.read_text(encoding="utf-8"))
                tool = table.get("tool", {})
                if not isinstance(tool, dict):
                    raise ValueError("[tool] must be a table")
                config = tool.get("oo-ratchet", {})
                if not isinstance(config, dict):
                    raise ValueError("[tool.oo-ratchet] must be a table")
                return config, parent
        return {}, Path.cwd()
