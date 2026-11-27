"""No function in the unit-3 modules takes more than four parameters."""

from __future__ import annotations

import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / "src" / "oo_ratchet"
LIMIT = 4
TOP_PREFIXES = (
    "source_",
    "sources",
    "gate_options",
    "usage",
    "logging_config",
    "backfill",
    "__main__",
    "gates",
)


def unit_files() -> list[Path]:
    """Return the coupling/, oo/ and listed top-level modules."""
    files = [*SOURCE.glob("coupling/**/*.py"), *SOURCE.glob("oo/**/*.py")]
    files += [p for p in SOURCE.glob("*.py") if p.name.startswith(TOP_PREFIXES)]
    return sorted(files)


def long_signatures() -> list[str]:
    """Return ``module.function (n)`` for each over-long signature."""
    found: list[str] = []
    for path in unit_files():
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            args = node.args
            names = [a.arg for a in args.posonlyargs + args.args + args.kwonlyargs]
            count = len([n for n in names if n not in ("self", "cls")])
            if count > LIMIT:
                found.append(f"{path.name}:{node.name} ({count})")
    return found


def test_no_function_takes_more_than_four_parameters() -> None:
    assert long_signatures() == []
