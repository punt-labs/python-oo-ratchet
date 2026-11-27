"""Count adopter modules that miss an absolute OO target, for two oo-ratchet builds.

The count covers the whole source tree: every module (excluding package __init__
files) is checked against the targets a new file must meet, using each build's
own thresholds. It is not limited to files a branch adds.
"""

from __future__ import annotations

import sys
from collections import Counter

from oo_json import failing_metrics, run_json, scored_rows

ADOPTER, SRC = sys.argv[1], sys.argv[2]
BUILDS = {"main": sys.argv[3], "branch": sys.argv[4]}

for label, checkout in BUILDS.items():
    data = run_json(["uvx", "--from", checkout, "oo-ratchet", "oo", SRC], cwd=ADOPTER)
    thresholds: dict[str, str] = data["thresholds"]
    failing_files = 0
    by_metric: Counter[str] = Counter()
    for row in scored_rows(data):
        fails = failing_metrics(row, thresholds)
        by_metric.update(fails)
        failing_files += bool(fails)
    print(f"{label:7} gated metrics: {len(thresholds):2}  modules missing a target "
          f"(whole tree): {failing_files}  by metric: {dict(by_metric.most_common())}")
