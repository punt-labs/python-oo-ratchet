# Dogfood: `layers --suggest` against the hand-written table

Command: `uv run oo-ratchet layers src/oo_ratchet --suggest` at `9f79987`
(179 modules). Summary line of the tool: 153 ring-assigned from a declaration
or name, 1 from entry evidence, 23 conflicts, 2 unclassified.

How to read it: `--suggest` treats the existing `[tool.oo-ratchet.layers]`
table as a declaration, so "agree" means the table's ring survived the
suggester's IO and import checks. It does not mean the suggester derived the
ring independently. The 153 agreeing modules carry the table's ring; the 25
others are where the suggester refused it.

## Agree (153 modules)

Every module the table assigns by an explicit pattern or by package name keeps
its ring with the evidence "reaches no IO" (domain, application) or "reaches
IO" (adapters, entry):

- entry (10): the package root, `__main__`, `gates`, `logging_config`, `usage`
  and the five `*.cli` modules.
- adapters (49): all of `core.adapters.*`, plus the `*.report`, `*.config`,
  `*.tree`, `*.gateinput`, `*.failures`, `*.suggest*`, `*.legacy_shadow`,
  `*.namespace_shadow`, `*.pyproject`, `design.enforcement.output`,
  `source_archive`, `source_history`, `source_set`, `sources`.
- application (21): `core.application.*`, `backfill`, `design.comparison`,
  `design.shadow_report`, `layers.chain`.
- domain (73): `core.domain.*` and the pure modules the `oo_ratchet.*`
  catch-all sweeps into domain (`design.*_rules`, `coupling.graph`,
  `coupling.metrics`, `layers.ring_*`, `oo.thresholds`, and so on).

## Conflicts (23) and a judgement for each

Sixteen of them are the sixteen source modules of the 30 baselined edges in
`.oo-layers-baseline.json`; the suggester and the gate agree on those.

| Module | What the suggester says | Judgement |
|---|---|---|
| `coupling` (`__init__`) | domain, but imports `coupling.cli` | Real violation (baselined). |
| `coupling.packages` | domain, imports `pathlib` | Real violation (baselined). |
| `coupling.scorer` | domain, imports `pathlib`, `source_set`, `config`, `tree` | Real violation (baselined); the module does file IO. |
| `design.scan` | application, imports `design.report` (adapters) and `source_set` | Real violation (baselined). |
| `design.scanner` | domain, reaches IO through `design.scan` | Real violation (baselined); follows from `design.scan`. |
| `design.shadow` | application, imports `legacy_shadow`, `namespace_shadow`, `source_set` | Real violation (baselined). |
| `design.shadow_scan` | application, imports `source_set` (adapters) | Real violation (baselined). |
| `layers` (`__init__`) | domain, imports `layers.cli` and `layers.scan` | Real violation (baselined). |
| `layers.scan` | application, imports `source_set` (adapters) | Real violation (baselined). |
| `layers.strict` | domain, imports `layers.chain` (application) | Real violation (baselined), or a table error: `chain` may belong in domain. For the lead. |
| `oo` (`__init__`) | domain, imports `oo.cli` | Real violation (baselined). |
| `oo.scorer` | domain, imports `json`, `pathlib`, `source_set` | Real violation (baselined). |
| `oo.code_lines` | domain, imports `io` | Not a code violation: it only calls `io.StringIO(source).readline`, which is in memory. The gate's IO list (`core/domain/domain_io.py`) counts `io`, so the edge is baselined. A rule-precision problem shared by gate and suggester, not a suggest bug. Narrowing it would shrink the baseline by 2. For the lead. |
| `suppression.patterns` | domain, imports `io` | Same as `oo.code_lines` (`io.StringIO`). |
| `suppression` (`__init__`) | domain, imports `suppression.cli`, `pyproject`, `report` | Real violation (baselined). |
| `suppression.scanner` | domain, imports `pathlib`, `source_set`, `pyproject`, `report` | Real violation (baselined). |
| `oo.metrics` | domain, reaches IO through `oo.code_lines -> io` | Follows from `oo.code_lines`; not in the baseline because the baseline holds direct edges only. |
| `design.size_rules` | same chain through `oo.code_lines` | Same. |
| `design.shape_rules` | chain through `size_rules` | Same. |
| `design.data_rules` | chain through `shape_rules` | Same. |
| `design.layers` | chain through `oo.metrics` | Same. |
| `design.output` | table says adapters, imports `argparse` | Table error, or a misplaced module: it parses and routes the design command line, which is entry work. The table cannot say it, because `oo_ratchet.*.output` is a general adapters pattern. For the lead. |
| `gate_options` | table says adapters, imports `argparse` | Table error: it builds the shared argparse parser (`GateOptions.parser`), which is entry. For the lead. |

Count: 16 baselined real violations, 5 transitive consequences of the `io`
rule, 2 argparse modules the table puts in the wrong ring.

## Unclassified (2)

| Module | Reason given | Judgement |
|---|---|---|
| `layers.diagram` | table says application; it imports `layers.scan`, which has no ring | By design. A module that imports a ring-less module cannot be judged, so the suggester drops its ring. It resolves when `layers.scan` is fixed. |
| `layers.package_edges` | table says domain; it imports `layers.strict`, which has no ring | Same, resolves when `layers.strict` is fixed. |

Cosmetic wart, not fixed: both reasons say "imports unclassified X", but X is
listed under Conflicts, not Unclassified. The wording is in
`layers/suggest_rules.py` (`_refusal`). No test pins it.

## Suggest bugs

None found that change a ring or a verdict. Every conflict traced to a real
import or to the gate's own IO list. No source file changed in this
work, so no baseline moved.

## Findings for the lead

1. 16 real violations are the existing baseline (30 edges); nothing new.
2. `io` in the gate's IO list flags in-memory `io.StringIO` use in two modules
   (`oo.code_lines`, `suppression.patterns`) and, through them, five more
   modules in the suggester's transitive view.
3. `gate_options` and `design.output` import `argparse` and sit in adapters;
   the table should place them in entry, or the argparse code should move into
   a `*.cli` module.
4. `layers.strict -> layers.chain`: decide whether `chain` is domain.
5. Running the new `check-design` gate against `HEAD~4` (before the A4 refactor
   commits) reports 6 added `layer-import` findings for `SourceSelection`
   (`design.scan`, `design.shadow`, `design.shadow_scan`, `layers.scan`,
   `oo.scorer`, `suppression.scanner` importing `source_set`). Against
   `origin/main` it reports none.
