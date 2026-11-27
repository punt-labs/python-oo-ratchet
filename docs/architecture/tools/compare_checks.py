"""Score every design-eval bad/good pair with the primary OO gate and the design check."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(sys.argv[1])


def meets(op: str, target: float, value: float) -> bool:
    if op == ">=":
        return value >= target
    if op == "<=":
        return value <= target
    return value == target


def run(*args: str) -> dict:
    """Run oo-ratchet with --json. Exit 1 is normal (a target failed); no JSON is not."""
    out = subprocess.run(
        ["oo-ratchet", *args, "--json"], cwd=REPO, capture_output=True, text=True
    )
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        sys.exit(f"oo-ratchet {' '.join(args)} produced no JSON (exit {out.returncode}): "
                 f"{(out.stderr or out.stdout).strip()}")


def primary_fails(src: str) -> list[str]:
    """Per-file target failures, using the gate's own thresholds from its output."""
    data = run("oo", src)
    targets = {m: rule.split() for m, rule in data["thresholds"].items()}
    fails = []
    for row in data["per_file"]:
        name = Path(row["file"]).name
        if name == "__init__.py":
            continue  # identical empty package markers on both sides
        for metric, (op, target) in targets.items():
            if not meets(op, float(target), row[metric]):
                fails.append(f"{name}:{metric}={row[metric]}")
    return fails


def design_findings(src: str, layers: Path | None) -> list[str]:
    extra = ["--layers", str(layers)] if layers else []
    data = run("design", src, *extra)
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
