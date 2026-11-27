"""Score every design-eval bad/good pair with the primary OO gate and the design check."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from oo_json import failing_metrics, run_json, scored_rows

REPO = Path(sys.argv[1])


def primary_fails(src: str) -> list[str]:
    """Per-file target failures, using the gate's own thresholds from its output."""
    data = run_json(["oo-ratchet", "oo", src], cwd=str(REPO))
    fails = []
    for row in scored_rows(data):
        name = Path(row["file"]).name
        for metric in failing_metrics(row, data["thresholds"]):
            fails.append(f"{name}:{metric}={row[metric]}")
    return fails


def design_findings(src: str, layers: Path | None) -> list[str]:
    extra = ["--layers", str(layers)] if layers else []
    # Scan a copy outside the checkout so the repository's own pyproject layer
    # table cannot reach the fixture through the ancestor lookup.
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / Path(src).name
        shutil.copytree(REPO / src, copy)
        data = run_json(["oo-ratchet", "design", str(copy), *extra], cwd=str(REPO))
    return [f"{Path(f['path']).name}:{f['rule']}" for f in data["findings"]]


def main() -> None:
    cases = sorted(p for p in (REPO / "evals/design").iterdir() if p.is_dir())
    print(f"{'case':16} {'side':5} {'files':>5} {'primary fails':>13} {'design findings':>15}")
    for case in cases:
        layers = case / "layers.toml"
        for side in ("bad", "good"):
            src = case / side / "loans"
            if not src.is_dir():
                continue
            rel = str(src.relative_to(REPO))
            files = len([p for p in src.rglob("*.py") if p.name != "__init__.py"])
            pf = primary_fails(rel)
            df = design_findings(rel, layers if layers.exists() else None)
            print(f"{case.name:16} {side:5} {files:>5} {len(pf):>13} {len(df):>15}")
            for item in pf:
                print(f"{'':28}primary  {item}")
            for item in df:
                print(f"{'':28}design   {item}")


main()
