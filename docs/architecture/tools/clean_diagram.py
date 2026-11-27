"""Lux draw element: oo_ratchet target in Clean Architecture form.

Rows are rings (entry, adapters, application, domain); columns are the shared
core and each gate as a vertical slice. Dependencies point down, toward domain.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path(sys.argv[1])

FG, GREY, HEAD, LABEL, EDGE = "#d8dee9", "#7f848e", "#61afef", "#e5c07b", "#abb2bf"
ROWS = [
    # key, title, fill, accent, note
    ("entry", "ENTRY", "#2c2f36", "#abb2bf", "wires adapters to operations"),
    ("adapters", "ADAPTERS", "#3a2f22", "#d19a66", "git, files, CLI, config"),
    ("application", "APPLICATION", "#232f3e", "#61afef", "operations + ports"),
    ("domain", "DOMAIN", "#243326", "#98c379", "pure rules: no IO"),
]
COLS = ["shared", "oo", "coupling", "suppression", "layers", "design"]
COL_TITLE = {
    "shared": "shared core", "oo": "oo gate", "coupling": "coupling gate",
    "suppression": "suppression gate", "layers": "clean layers gate",
    "design": "design (advisory)",
}

CELLS: dict[tuple[str, str], list[str]] = {
    ("entry", "shared"): ["Dispatcher (__main__)", "gate registry: builds each", "gate from its adapters"],
    ("adapters", "shared"): [
        "GitRepo  -> History", "JsonBaselineStore", "  -> BaselineStore",
        "AuditFile -> AuditSink", "SourceTree -> SourceReader", "PyprojectConfig",
        "GateCli, text/--json report", "DiagnosticLog, Usage",
    ],
    ("adapters", "oo"): ["OO baseline format", "OO report rows"],
    ("adapters", "coupling"): ["coupling baseline", "format", "caps config reader"],
    ("adapters", "suppression"): ["suppression baseline", "format", "ruff per-file-ignores", "reader"],
    ("adapters", "layers"): ["layers baseline format", "ring table reader", "([tool.oo-ratchet.layers]", " entry/adapters/", " application/domain)"],
    ("adapters", "design"): ["ShadowWorktree", "(base checkout)", "findings report"],
    ("application", "shared"): [
        "operations, written once:", "  Check, Update, Relax,", "  RebaselineFiles, Rebaseline",
        "ports (Protocols):", "  History, BaselineStore,", "  AuditSink, SourceReader",
        "GatePolicy (Protocol)",
    ],
    ("application", "oo"): ["MustImprove policy", "(no regression, one", "improvement)"],
    ("application", "coupling"): ["RegressionOnly policy"],
    ("application", "suppression"): ["TotalMayNotRise policy"],
    ("application", "layers"): ["MayOnlyShrink policy:", "violations may only", "shrink vs merge base;", "no unassigned module"],
    ("application", "design"): ["ShadowCheck", "(new findings vs base;", "advisory)"],
    ("domain", "shared"): [
        "Score, BaselineRow", "Review, Verdict, Waiver", "AuditRecord", "Diff (renames as data)",
        "SourceSelection", "LayerModel: LayerConfig,", "  Edge, Violation,",
        "  ModuleIndex (layers+design)",
    ],
    ("domain", "oo"): ["ModuleMetrics, CodeLines", "MetricRule x8", "  (module_size ceiling)", "FileReview"],
    ("domain", "coupling"): ["ImportGraph, Lcom", "ClassState", "MetricRule x5", "CouplingReview"],
    ("domain", "suppression"): ["SuppressionCount", "MarkerPatterns"],
    ("domain", "layers"): ["DependencyRule:", "  imports point inward", "DomainPurity: domain", "  imports no IO", "  (was advisory", "  domain-io)", "LayerScan"],
    ("domain", "design"): ["ClassRules, DataRules,", "EnvyRules, SizeRules", "Finding, DesignDebt"],
}

LINE = 17
X0, LABEL_W, X1 = 20, 150, 1440
COL_W = (X1 - X0 - LABEL_W) / len(COLS)
TOP = 120

cmds: list[dict[str, object]] = []


def text(x: float, y: float, s: str, color: str = FG) -> None:
    cmds.append({"cmd": "text", "pos": [x, y], "text": s, "color": color})


# column headers
for i, col in enumerate(COLS):
    cx = X0 + LABEL_W + i * COL_W
    text(cx + 8, TOP - 22, COL_TITLE[col], HEAD if col != "shared" else LABEL)

y = TOP
row_y: dict[str, tuple[float, float]] = {}
for key, title, fill, accent, note in ROWS:
    lines = max(len(CELLS.get((key, c), [])) for c in COLS)
    h = 14 + LINE * max(lines, 3)
    row_y[key] = (y, y + h)
    cmds.append({"cmd": "rect", "min": [X0, y], "max": [X1, y + h], "color": fill,
                 "filled": True, "rounding": 4})
    cmds.append({"cmd": "rect", "min": [X0, y], "max": [X1, y + h], "color": accent,
                 "thickness": 1.5, "rounding": 4})
    text(X0 + 10, y + 8, title, accent)
    text(X0 + 10, y + 8 + LINE, note, GREY)
    for i, col in enumerate(COLS):
        cx = X0 + LABEL_W + i * COL_W
        cmds.append({"cmd": "line", "p1": [cx, y], "p2": [cx, y + h],
                     "color": accent, "thickness": 0.8})
        for j, s in enumerate(CELLS.get((key, col), [])):
            text(cx + 8, y + 7 + LINE * j, s)
    y += h + 26

# dependency arrows in the gaps between rows (pointing inward = down)
order = [r[0] for r in ROWS]
for upper, lower in zip(order, order[1:], strict=False):
    gy0, gy1 = row_y[upper][1], row_y[lower][0]
    for x in (X0 + 60, X0 + LABEL_W + 3.5 * COL_W):
        cmds.append({"cmd": "line", "p1": [x, gy0 + 2], "p2": [x, gy1 - 2],
                     "color": EDGE, "thickness": 2.5})
        cmds.append({"cmd": "triangle", "p1": [x, gy1 - 1], "p2": [x - 6, gy1 - 11],
                     "p3": [x + 6, gy1 - 11], "color": EDGE, "filled": True})
    text(X0 + 72, gy0 + 4, "depends on", GREY)

# "implements" link: GitRepo (adapters, shared) -> History port (application, shared)
ax = X0 + LABEL_W + COL_W - 24
a0, a1 = row_y["adapters"][0] + 10, row_y["application"][0] + 4 + LINE * 4
cmds.append({"cmd": "polyline", "points": [[ax, a0], [ax + 14, a0], [ax + 14, a1], [ax, a1]],
             "color": LABEL, "thickness": 1.6})
cmds.append({"cmd": "triangle", "p1": [ax, a1], "p2": [ax + 10, a1 - 5], "p3": [ax + 10, a1 + 5],
             "color": LABEL, "filled": True})

# title and notes
text(X0, 16, "oo_ratchet TARGET in Clean Architecture form (proposed)", HEAD)
text(X0, 36, "rows are rings; dependencies point down, toward the domain. "
     "Each gate is a vertical slice through the rings.", FG)
text(X0, 54, "Adapters implement the application's ports (orange bracket: "
     "GitRepo implements History). The domain imports no git, files, json or os.", FG)
text(X0, 72, "Enforced on itself by the clean layers ratchet: inward-only imports plus "
     "domain purity, a violation baseline that may only shrink.", GREY)
text(X0, y + 4, "gone vs today: 4 GitRepo copies, 4 Outcome, 5 Options, 5 Cli, 3 audit logs "
     "-> one each in the shared column; layers no longer imports design.", GREY)

element = {"kind": "draw", "id": "clean", "width": 1460, "height": int(y + 30),
           "bg_color": "#21252b", "commands": cmds}
OUT.write_text(json.dumps(element))
print(len(cmds), int(y + 30))
