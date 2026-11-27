"""Lux draw element: oo_ratchet TARGET state after plan levels 1-3."""

from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path(sys.argv[1])

FG, HEAD, GREEN, GREY, EDGE, LABEL = (
    "#d8dee9", "#61afef", "#98c379", "#7f848e", "#5c6370", "#e5c07b",
)
NEW = "#2d3b2d"  # fill for a new package

# (title, x0, y0, x1, lines, new_package)
# A line is (text, color). GREEN = new or moved here; FG = kept, reshaped; GREY = gone.
BOXES: dict[str, tuple[str, int, int, int, list[tuple[str, str]], bool]] = {
    "entry": ("entry  (__main__, gates)", 560, 14, 900, [
        ("Dispatcher", FG),
    ], False),
    "layers": ("layers  (gate)", 20, 110, 700, [
        ("LayersRatchet, LayersWriter, LayersBaseline", FG),
        ("LayerScan  - decides its own verdicts (was getter-heavy)", FG),
        ("gone: BaseTree (middle-man), ImportArgs (function bag)", GREY),
        ("gone: own Cli, Options, Outcome, GitRepo -> core", GREY),
    ], False),
    "design": ("design  (advisory rules, shadow check)", 740, 110, 1440, [
        ("ClassRules, DataRules, EnvyRules, SizeRules, ShadowCheck", FG),
        ("DataInventory  - split by what it inventories (was split-cohesion)", FG),
        ("gone: Rules, TypeReference (single-method shells)", GREY),
        ("moved out: LayerConfig, LayerTable, ModuleIndex, Module -> layering", GREY),
    ], False),
    "layering": ("layering  (NEW)", 20, 330, 360, [
        ("LayerConfig", GREEN),
        ("LayerTable  - holds the config it reads", GREEN),
        ("ModuleIndex, Module (owns its reads)", GREEN),
        ("Edge, Violation, LayerViolations", GREEN),
    ], True),
    "oo": ("oo  (gate)", 380, 330, 720, [
        ("Ratchet, Scorer, BaselineWriter", FG),
        ("FileReview  - decides, callers ask", FG),
        ("MetricRule x8  (was Thresholds bag)", GREEN),
        ("gone: own GitRepo, Cli, Options, Outcome", GREY),
    ], False),
    "coupling": ("coupling  (gate)", 740, 330, 1080, [
        ("CouplingRatchet, CouplingScorer", FG),
        ("CouplingReview  - decides, callers ask", FG),
        ("ClassState  (was PrivateState bag)", GREEN),
        ("MetricRule x5  (was CouplingThresholds)", GREEN),
        ("gone: PackageLayout middle-man, own GitRepo", GREY),
    ], False),
    "suppression": ("suppression  (gate)", 1100, 330, 1440, [
        ("SuppressionBaseline, Scanner", FG),
        ("BaselineFile", FG),
        ("gone: own GitRepo, Cli, Options, Outcome", GREY),
    ], False),
    "core": ("core  (shared ratchet core)", 20, 600, 1440, [
        ("GitRepo, GitError, Diff  - one copy (were 4 GitRepo copies)", GREEN),
        ("Outcome  - one copy (was 4)", GREEN),
        ("AuditLog + AuditRecord  - one log, append(record) (were 3 logs, 9-param append)", GREEN),
        ("GateOptions, GateCli  - one option set (were 5 Options, 5 Cli)", GREEN),
        ("SourceSelection, SourceHistory, SourceArchive  (was SourceSet, 28 methods)", GREEN),
        ("Sources, Backfill, Usage, DiagnosticLog", FG),
    ], False),
}

LINE = 18
cmds: list[dict[str, object]] = []
geom: dict[str, tuple[int, int, int, int]] = {}
for key, (title, x0, y0, x1, lines, new) in BOXES.items():
    y1 = y0 + 30 + LINE * len(lines) + 6
    geom[key] = (x0, y0, x1, y1)
    border = GREEN if new else HEAD
    cmds.append({"cmd": "rect", "min": [x0, y0], "max": [x1, y1],
                 "color": NEW if new else "#282c34", "filled": True, "rounding": 6})
    cmds.append({"cmd": "rect", "min": [x0, y0], "max": [x1, y1], "color": border,
                 "thickness": 2.0 if new else 1.5, "rounding": 6})
    cmds.append({"cmd": "text", "pos": [x0 + 10, y0 + 6], "text": title, "color": border})
    cmds.append({"cmd": "line", "p1": [x0, y0 + 25], "p2": [x1, y0 + 25],
                 "color": border, "thickness": 1})
    for i, (text, color) in enumerate(lines):
        cmds.append({"cmd": "text", "pos": [x0 + 14, y0 + 31 + LINE * i],
                     "text": text, "color": color})


def arrow(points: list[list[float]], label: str, label_at: list[float]) -> None:
    cmds.append({"cmd": "polyline", "points": points, "color": EDGE, "thickness": 2.2})
    (ax, ay), (bx, by) = points[-2], points[-1]
    dx, dy = bx - ax, by - ay
    n = (dx * dx + dy * dy) ** 0.5 or 1
    ux, uy, px, py = dx / n, dy / n, -dy / n, dx / n
    cmds.append({"cmd": "triangle", "p1": [bx, by],
                 "p2": [bx - 12 * ux + 6 * px, by - 12 * uy + 6 * py],
                 "p3": [bx - 12 * ux - 6 * px, by - 12 * uy - 6 * py],
                 "color": EDGE, "filled": True})
    cmds.append({"cmd": "text", "pos": label_at, "text": label, "color": LABEL})


def bottom(k: str) -> int:
    return geom[k][3]


def top(k: str) -> int:
    return geom[k][1]


# layers -> layering, layers -> core (through the gap at x=370)
arrow([[190, bottom("layers")], [190, top("layering")]], "LayerConfig, Edge, ModuleIndex",
      [198, bottom("layers") + 4])
arrow([[600, bottom("layers")], [600, 300], [370, 300], [370, top("core")]],
      "GitRepo, Outcome, AuditLog", [430, 282])
# design -> layering, oo, coupling, core (through the gap at x=1090)
arrow([[800, bottom("design")], [300, top("layering")]], "rules read layers",
      [470, bottom("design") + 8])
arrow([[900, bottom("design")], [600, top("oo")]], "Scorer, FileReview (shadow)",
      [640, top("oo") - 34])
arrow([[1000, bottom("design")], [960, top("coupling")]], "coupling metrics",
      [990, top("coupling") - 22])
arrow([[1300, bottom("design")], [1300, 310], [1090, 310], [1090, top("core")]],
      "core", [1100, 292])
# every lower package -> core
for k in ("layering", "oo", "coupling", "suppression"):
    x0, _, x1, y1 = geom[k]
    cx = (x0 + x1) // 2
    arrow([[cx, y1], [cx, top("core")]], "", [cx, y1])

# legend
cmds += [
    {"cmd": "text", "pos": [20, 14], "text": "oo_ratchet TARGET (proposed): plan levels 1-3",
     "color": HEAD},
    {"cmd": "text", "pos": [20, 32], "text": "green: new class or package", "color": GREEN},
    {"cmd": "text", "pos": [20, 50], "text": "white: kept, reshaped", "color": FG},
    {"cmd": "text", "pos": [20, 68], "text": "grey: removed or moved away", "color": GREY},
    {"cmd": "text", "pos": [920, 20],
     "text": "entry imports each gate's cli (not drawn)", "color": GREY},
    {"cmd": "text", "pos": [920, 40],
     "text": "removed edges: layers -> design (22), layers -> coupling (7)", "color": GREY},
    {"cmd": "text", "pos": [20, bottom("core") + 14],
     "text": "dependencies only point down: entry -> gates -> layering -> core; "
             "duplicated class names across gates: 7 -> 0",
     "color": GREY},
]

element = {"kind": "draw", "id": "target", "width": 1460,
           "height": bottom("core") + 44, "bg_color": "#21252b", "commands": cmds}
OUT.write_text(json.dumps(element))
print(len(cmds), element["height"])
