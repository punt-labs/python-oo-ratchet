"""Count per-file OO target failures on an adopter, for two oo-ratchet builds."""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter

ADOPTER, SRC = sys.argv[1], sys.argv[2]
BUILDS = {"main": sys.argv[3], "branch": sys.argv[4]}

for label, checkout in BUILDS.items():
    cmd = ["uvx", "--from", checkout, "oo-ratchet", "oo", SRC, "--json"]
    out = subprocess.run(cmd, cwd=ADOPTER, capture_output=True, text=True, check=False)
    data = json.loads(out.stdout)
    thresholds = data["thresholds"]
    failing_files = 0
    by_metric: Counter[str] = Counter()
    for row in data["per_file"]:
        if row["file"].endswith("__init__.py"):
            continue
        fails = []
        for metric, rule in thresholds.items():
            op, target = rule.split()
            value, limit = float(row[metric]), float(target)
            ok = {">=": value >= limit, "<=": value <= limit, "==": value == limit}[op]
            if not ok:
                fails.append(metric)
        by_metric.update(fails)
        failing_files += bool(fails)
    print(f"{label:7} gated metrics: {len(thresholds):2}  modules failing a target: "
          f"{failing_files}  by metric: {dict(by_metric.most_common())}")
