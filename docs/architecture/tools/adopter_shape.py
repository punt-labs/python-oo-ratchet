"""Summarize module sizes (primary gate) and design findings for one adopter package."""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter

from oo_json import run_json, scored_rows

SRC = sys.argv[1]

oo = run_json(["oo-ratchet", "oo", SRC])
rows = scored_rows(oo)
if not rows:
    sys.exit(f"no scored modules under {SRC}")
ceiling = int(float(str(oo["thresholds"]["module_size"]).split()[1]))
sizes = sorted(int(r["module_size"]) for r in rows)
classes = Counter(int(r["classes_per_module"]) for r in rows)
print(f"modules (excl. __init__): {len(sizes)}")
print(f"module_size median {statistics.median(sizes)}, p25 {sizes[len(sizes) // 4]}, "
      f"p75 {sizes[3 * len(sizes) // 4]}, max {sizes[-1]}")
print(f"modules <= 40 code lines: {sum(s <= 40 for s in sizes)}")
print(f"modules > {ceiling} (module_size ceiling): {sum(s > ceiling for s in sizes)}")
print(f"classes per module: {dict(sorted(classes.items()))}")

design = run_json(["oo-ratchet", "design", SRC])
counts = {k: v for k, v in design["counts"].items() if v}
print(f"design files scanned: {design['files_scanned']}")
print("design findings:", json.dumps(counts, sort_keys=True))
