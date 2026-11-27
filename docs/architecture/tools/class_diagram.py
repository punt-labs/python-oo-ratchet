"""Build a lux draw element: oo_ratchet packages, key classes, import edges."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(sys.argv[1])
ROOT = REPO / "src" / "oo_ratchet"
OUT = Path(sys.argv[2])

ENTRY = {"__main__", "gates"}
GATES = {"oo", "coupling", "suppression", "design", "layers"}


def group_of(module: str) -> str:
    """Map a dotted module (oo_ratchet.x.y) to its diagram group."""
    parts = module.split(".")
    top = parts[1] if len(parts) > 1 else "__init__"
    if top in GATES:
        return top
    if top in ENTRY:
        return "entry"
    return "core"


def module_name(path: Path) -> str:
    parts = list(path.relative_to(ROOT.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def resolve(node: ast.ImportFrom, here: str, is_pkg: bool) -> str | None:
    if node.level == 0:
        return node.module
    base = here.split(".")
    if not is_pkg:
        base = base[:-1]
    base = base[: len(base) - (node.level - 1)]
    return ".".join(base + ([node.module] if node.module else []))


# --- classes per group, with method counts ---------------------------------
classes: dict[str, list[tuple[str, int]]] = defaultdict(list)
edges: Counter[tuple[str, str]] = Counter()
names_by_group: dict[str, set[str]] = defaultdict(set)
for path in sorted(ROOT.rglob("*.py")):
    here = module_name(path)
    grp = group_of(here if path.name != "__init__.py" else here + ".x")
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = sum(
                isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in node.body
            )
            classes[grp].append((node.name, methods))
            names_by_group[grp].add(node.name)
    for node in ast.walk(tree):
        targets: list[str] = []
        if isinstance(node, ast.Import):
            targets = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mod = resolve(node, here, path.name == "__init__.py")
            targets = [mod] if mod else []
        for t in targets:
            if t.startswith("oo_ratchet."):
                dst = group_of(t)
                if dst != grp:
                    edges[(grp, dst)] += 1

# --- class names defined in more than one gate (duplicated infrastructure) --
seen: Counter[str] = Counter()
for grp, names in names_by_group.items():
    seen.update(names)
duplicated = {n for n, c in seen.items() if c > 1}

# --- classes the design check flags ------------------------------------------
_run = subprocess.run(
    ["uv", "run", "oo-ratchet", "design", "src/oo_ratchet/", "--json"],
    cwd=REPO, capture_output=True, text=True, check=False,
)
try:
    design = json.loads(_run.stdout)
except json.JSONDecodeError:
    sys.exit(f"oo-ratchet design produced no JSON (exit {_run.returncode}): "
             f"{(_run.stderr or _run.stdout).strip()}")
CLASS_RULES = {
    "stateless-function-bag", "stateless-single-method", "middle-man",
    "getter-heavy", "split-cohesion", "envied-data", "size-cap",
}
flagged: dict[str, str] = {}
for f in design["findings"]:
    if f["rule"] in CLASS_RULES and "." not in f["symbol"] and f["symbol"] != "<module>":
        flagged.setdefault(f["symbol"], f["rule"])

# --- layout ------------------------------------------------------------------
W, H = 1460, 1010
BOX_W = 420
LINE = 17
POS = {
    "entry": (520, 14),
    "layers": (520, 150),
    "design": (520, 345),
    "oo": (40, 590),
    "coupling": (520, 590),
    "suppression": (1000, 590),
    "core": (520, 815),
}
TITLE = {
    "entry": "entry  (__main__, gates)",
    "layers": "layers",
    "design": "design  (advisory)",
    "oo": "oo",
    "coupling": "coupling",
    "suppression": "suppression",
    "core": "core  (source_*, backfill, usage, logging)",
}
MAX_LINES = {"entry": 3, "layers": 6, "design": 7, "core": 6}

FG, HEAD, RED, ORANGE, GREY, EDGE = (
    "#d8dee9", "#61afef", "#e06c75", "#d19a66", "#7f848e", "#5c6370",
)

cmds: list[dict[str, object]] = []
boxes: dict[str, tuple[float, float, float, float]] = {}
for grp, (x, y) in POS.items():
    items = sorted(
        classes[grp],
        key=lambda c: (c[0] not in flagged and c[0] not in duplicated, -c[1], c[0]),
    )
    shown = items[: MAX_LINES.get(grp, 7)]
    h = 28 + LINE * len(shown) + (LINE if len(items) > len(shown) else 0) + 6
    boxes[grp] = (x, y, x + BOX_W, y + h)
    cmds.append({"cmd": "rect", "min": [x, y], "max": [x + BOX_W, y + h],
                 "color": "#282c34", "filled": True, "rounding": 6})
    cmds.append({"cmd": "rect", "min": [x, y], "max": [x + BOX_W, y + h],
                 "color": HEAD, "thickness": 1.5, "rounding": 6})
    cmds.append({"cmd": "text", "pos": [x + 10, y + 6],
                 "text": f"{TITLE[grp]}   [{len(items)} classes]", "color": HEAD})
    cmds.append({"cmd": "line", "p1": [x, y + 24], "p2": [x + BOX_W, y + 24],
                 "color": HEAD, "thickness": 1})
    for i, (name, n) in enumerate(shown):
        tag, color = "", FG
        if name in flagged:
            tag, color = f"  <- {flagged[name]}", RED
        elif name in duplicated:
            tag, color = "  <- also defined in another gate", ORANGE
        cmds.append({"cmd": "text", "pos": [x + 14, y + 30 + LINE * i],
                     "text": f"{name} ({n} methods){tag}", "color": color})
    if len(items) > len(shown):
        cmds.append({"cmd": "text", "pos": [x + 14, y + 30 + LINE * len(shown)],
                     "text": f"... {len(items) - len(shown)} more", "color": GREY})


def anchor(grp: str, toward: str) -> tuple[float, float]:
    x0, y0, x1, y1 = boxes[grp]
    tx0, ty0, tx1, ty1 = boxes[toward]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    tcx = (tx0 + tx1) / 2
    if ty0 >= y1:  # target below
        return (min(max(tcx, x0 + 30), x1 - 30), y1)
    if ty1 <= y0:  # target above
        return (min(max(tcx, x0 + 30), x1 - 30), y0)
    return (x1, cy) if tcx > cx else (x0, cy)


MIDDLE = ["layers", "design", "coupling", "core"]
lane = 0
for (src, dst), n in sorted(edges.items()):
    if src == "entry":
        continue  # entry wires every gate; drawn as one note instead
    thick = 1.5 + min(n, 22) / 5
    if src in MIDDLE and dst in MIDDLE and MIDDLE.index(dst) - MIDDLE.index(src) > 1:
        # Skips a level: route down a lane right of the middle column.
        sx0, sy0, sx1, sy1 = boxes[src]
        dx0, dy0, dx1, dy1 = boxes[dst]
        lx = sx1 + 16 + 16 * lane
        lane += 1
        sy = (sy0 + sy1) / 2 + 10 * lane
        ey = (dy0 + dy1) / 2 - 10 * lane
        cmds.append({"cmd": "polyline", "points": [[sx1, sy], [lx, sy], [lx, ey], [dx1, ey]],
                     "color": EDGE, "thickness": thick})
        cmds.append({"cmd": "triangle", "p1": [dx1, ey], "p2": [dx1 + 12, ey - 6],
                     "p3": [dx1 + 12, ey + 6], "color": EDGE, "filled": True})
        cmds.append({"cmd": "text", "pos": [lx + 4, (sy + ey) / 2 + 14 * lane],
                     "text": f"{n}", "color": "#e5c07b"})
        continue
    sx, sy = anchor(src, dst)
    ex, ey = anchor(dst, src)
    cmds.append({"cmd": "line", "p1": [sx, sy], "p2": [ex, ey], "color": EDGE,
                 "thickness": thick})
    dx, dy = ex - sx, ey - sy
    length = (dx * dx + dy * dy) ** 0.5 or 1
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    tip = (ex, ey)
    cmds.append({"cmd": "triangle", "p1": list(tip),
                 "p2": [ex - 12 * ux + 6 * px, ey - 12 * uy + 6 * py],
                 "p3": [ex - 12 * ux - 6 * px, ey - 12 * uy - 6 * py],
                 "color": EDGE, "filled": True})
    mx, my = sx + dx * 0.45, sy + dy * 0.45
    cmds.append({"cmd": "text", "pos": [mx + 6, my - 8], "text": f"{n} imports",
                 "color": "#e5c07b"})

ex0, ey0, ex1, ey1 = boxes["entry"]
cmds.append({"cmd": "text", "pos": [ex1 + 14, ey0 + 8],
             "text": "entry imports every gate's cli (not drawn)", "color": GREY})

# legend
lx, ly = 30, 20
cmds.append({"cmd": "text", "pos": [lx, ly], "text": "oo_ratchet: packages and key classes",
             "color": HEAD})
cmds.append({"cmd": "text", "pos": [lx, ly + 22], "text": "red: flagged by the design check",
             "color": RED})
cmds.append({"cmd": "text", "pos": [lx, ly + 40],
             "text": "orange: same class name defined in another gate", "color": ORANGE})
cmds.append({"cmd": "text", "pos": [lx, ly + 58],
             "text": "arrow: package imports package (count)", "color": "#e5c07b"})
cmds.append({"cmd": "text", "pos": [lx, ly + 76],
             "text": "no import cycles between packages", "color": GREY})

element = {"kind": "draw", "id": "classes", "width": W, "height": H,
           "bg_color": "#21252b", "commands": cmds}
OUT.write_text(json.dumps(element))
print(f"commands: {len(cmds)}; edges: {dict(edges)}; duplicated: {sorted(duplicated)}")
