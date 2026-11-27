"""Build a lux draw element: the four rings, their modules and the layer violations.

Usage: layers_diagram.py <repo> <out.json> [rings.toml]

Reads ``oo-ratchet layers --json`` (module_rings, ring_edges, marked_violations)
instead of scanning imports itself. The ring table is
docs/architecture/four-rings.toml unless a third argument names another; it is
copied with the package into a scratch git repository, so the repo's own
pyproject.toml is never read or changed. Run with ``uv run --directory <repo>
python ...`` (it calls ``oo-ratchet``).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

REPO = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2])
RINGS = Path(sys.argv[3]) if len(sys.argv) > 3 else REPO / "docs/architecture/four-rings.toml"
PACKAGE = "oo_ratchet"


def layers_json() -> dict[str, object]:
    """Run ``oo-ratchet layers --json`` on a scratch copy carrying the ring table."""
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        shutil.copytree(
            REPO / "src" / PACKAGE,
            scratch / "src" / PACKAGE,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        shutil.copy(RINGS, scratch / "pyproject.toml")
        subprocess.run(["git", "init", "-q"], cwd=scratch, check=True)
        run = subprocess.run(
            ["uv", "run", "--directory", str(REPO), "oo-ratchet", "layers",
             str(scratch / "src" / PACKAGE), "--json"],
            capture_output=True, text=True, check=False,
        )
    try:
        data: dict[str, object] = json.loads(run.stdout)
    except json.JSONDecodeError:
        sys.exit(f"oo-ratchet layers produced no JSON (exit {run.returncode}): "
                 f"{(run.stderr or run.stdout).strip()}")
    return data


data = layers_json()
rings: dict[str, str | None] = data["module_rings"]  # type: ignore[assignment]
ring_edges: list[dict[str, object]] = data["ring_edges"]  # type: ignore[assignment]
marked: list[dict[str, str]] = data["marked_violations"]  # type: ignore[assignment]

ORDER = ["entry", "adapters", "application", "domain"]
members = Counter(r or "unassigned" for r in rings.values())
sources: dict[str, Counter[str]] = {r: Counter() for r in ORDER}
for v in marked:
    sources[v["source_ring"]][v["source"]] += 1
io_edges = [v for v in marked if v["kind"] == "io"]

FG, HEAD, RED, GREY, GOLD = "#d8dee9", "#61afef", "#e06c75", "#7f848e", "#e5c07b"
W, H = 1100, 760
BOX_X, BOX_W, BOX_H, GAP, TOP = 330, 440, 120, 50, 70
LINE = 17
box_y = {ring: TOP + i * (BOX_H + GAP) for i, ring in enumerate(ORDER)}
cmds: list[dict[str, object]] = []

for ring in ORDER:
    y = box_y[ring]
    cmds.append({"cmd": "rect", "min": [BOX_X, y], "max": [BOX_X + BOX_W, y + BOX_H],
                 "color": "#282c34", "filled": True, "rounding": 6})
    cmds.append({"cmd": "rect", "min": [BOX_X, y], "max": [BOX_X + BOX_W, y + BOX_H],
                 "color": HEAD, "thickness": 1.5, "rounding": 6})
    cmds.append({"cmd": "text", "pos": [BOX_X + 10, y + 6],
                 "text": f"{ring}   [{members[ring]} modules]", "color": HEAD})
    cmds.append({"cmd": "line", "p1": [BOX_X, y + 24], "p2": [BOX_X + BOX_W, y + 24],
                 "color": HEAD, "thickness": 1})
    worst = sources[ring].most_common(4)
    for i, (module, n) in enumerate(worst):
        cmds.append({"cmd": "text", "pos": [BOX_X + 14, y + 30 + LINE * i],
                     "text": f"{module.removeprefix(PACKAGE + '.')}  ({n} violating)",
                     "color": RED})
    if not worst:
        cmds.append({"cmd": "text", "pos": [BOX_X + 14, y + 30],
                     "text": "no violating module", "color": GREY})

# Violating edges point outward (to a ring above the source): draw them on the
# right of the stack, one lane per ring pair, arrow at the imported ring.
for lane, edge in enumerate(ring_edges):
    src, dst, n = str(edge["source_ring"]), str(edge["target_ring"]), edge["count"]
    if src not in box_y or dst not in box_y:
        continue
    x = BOX_X + BOX_W + 30 + 40 * lane
    sy = box_y[src] + BOX_H / 2
    ey = box_y[dst] + BOX_H / 2
    cmds.append({"cmd": "polyline",
                 "points": [[BOX_X + BOX_W, sy], [x, sy], [x, ey], [BOX_X + BOX_W, ey]],
                 "color": RED, "thickness": 2})
    cmds.append({"cmd": "triangle", "p1": [BOX_X + BOX_W, ey],
                 "p2": [BOX_X + BOX_W + 12, ey - 6], "p3": [BOX_X + BOX_W + 12, ey + 6],
                 "color": RED, "filled": True})
    cmds.append({"cmd": "text", "pos": [x + 4, (sy + ey) / 2],
                 "text": f"{src} -> {dst}: {n}", "color": GOLD})

total = sum(int(str(e["count"])) for e in ring_edges)
cmds.append({"cmd": "text", "pos": [30, 20], "text": "oo_ratchet: the four rings",
             "color": HEAD})
cmds.append({"cmd": "text", "pos": [30, 42],
             "text": f"red arrow: layer import the rings forbid, {total} in all",
             "color": RED})
cmds.append({"cmd": "text", "pos": [30, 60],
             "text": f"domain imports IO (purity): {len(io_edges)}; "
                     f"modules in no ring: {members['unassigned']}",
             "color": GREY})

element = {"kind": "draw", "id": "layers", "width": W, "height": H,
           "bg_color": "#21252b", "commands": cmds}
OUT.write_text(json.dumps(element))
print(f"commands: {len(cmds)}; ring edges: {ring_edges}; layer violations: {total}; "
      f"io edges: {len(io_edges)}")
