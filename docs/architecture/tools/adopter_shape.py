"""Summarize module sizes (primary gate) and design findings for one adopter package."""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
from collections import Counter

SRC = sys.argv[1]


def run(*args: str) -> dict[str, object]:
    """Run oo-ratchet with --json. Exit 1 is normal (a target failed); no JSON is not."""
    out = subprocess.run(
        ["oo-ratchet", *args, "--json"], capture_output=True, text=True, check=False
    )
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        sys.exit(f"oo-ratchet {' '.join(args)} produced no JSON (exit {out.returncode}): "
                 f"{(out.stderr or out.stdout).strip()}")


oo = run("oo", SRC)
rows = [r for r in oo["per_file"] if not r["file"].endswith("__init__.py")]  # type: ignore[index]
if not rows:
    sys.exit(f"no scored modules under {SRC}")
ceiling = int(float(str(oo["thresholds"]["module_size"]).split()[1]))  # type: ignore[index]
sizes = sorted(int(r["module_size"]) for r in rows)
classes = Counter(int(r["classes_per_module"]) for r in rows)
print(f"modules (excl. __init__): {len(sizes)}")
print(f"module_size median {statistics.median(sizes)}, p25 {sizes[len(sizes) // 4]}, "
      f"p75 {sizes[3 * len(sizes) // 4]}, max {sizes[-1]}")
print(f"modules <= 40 code lines: {sum(s <= 40 for s in sizes)}")
print(f"modules > {ceiling} (module_size ceiling): {sum(s > ceiling for s in sizes)}")
print(f"classes per module: {dict(sorted(classes.items()))}")

design = run("design", SRC)
counts = {k: v for k, v in design["counts"].items() if v}  # type: ignore[union-attr]
print(f"design files scanned: {design['files_scanned']}")
print("design findings:", json.dumps(counts, sort_keys=True))
