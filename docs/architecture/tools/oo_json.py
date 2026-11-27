"""Shared helpers for the measurement scripts: run oo-ratchet --json and read its rows.

Target checks use the `thresholds` block of the same run, so a script judges each
build by that build's own targets. `meets` mirrors `Thresholds.meets` in
`src/oo_ratchet/oo/thresholds.py`: a target is `<op> <value>`, and a ceiling metric
renders as `<= <value>` like any other upper bound, so the absolute check is the
same comparison.
"""

from __future__ import annotations

import json
import operator
import subprocess
import sys
from collections.abc import Callable, Sequence
from typing import Any

_OPS: dict[str, Callable[[float, float], bool]] = {
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
}


def run_json(cmd: Sequence[str], cwd: str | None = None) -> dict[str, Any]:
    """Run an oo-ratchet command with --json. Exit 1 is normal (a target failed);
    a missing executable or output that is not JSON stops the script with a message."""
    try:
        out = subprocess.run([*cmd, "--json"], cwd=cwd, capture_output=True, text=True,
                             check=False)
    except OSError as exc:
        sys.exit(f"cannot run {cmd[0]}: {exc}")
    try:
        data: dict[str, Any] = json.loads(out.stdout)
    except json.JSONDecodeError:
        sys.exit(f"{' '.join(cmd)} produced no JSON (exit {out.returncode}): "
                 f"{(out.stderr or out.stdout).strip()}")
    return data


def scored_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-file rows, excluding package __init__ files. A file the scorer could not
    read stops the script with the scorer's own message."""
    errors = [f"{r['file']}: {r['error']}" for r in data["per_file"] if "error" in r]
    if errors:
        sys.exit("oo-ratchet could not score:\n  " + "\n  ".join(errors))
    return [r for r in data["per_file"] if not str(r["file"]).endswith("__init__.py")]


def meets(rule: str, value: float) -> bool:
    """True when `value` meets a rendered target such as `<= 4.0`."""
    op, limit = rule.split()
    return _OPS[op](float(value), float(limit))


def failing_metrics(row: dict[str, Any], thresholds: dict[str, str]) -> list[str]:
    """The metrics of one row that miss their target."""
    return [m for m, rule in thresholds.items() if not meets(rule, row[m])]
