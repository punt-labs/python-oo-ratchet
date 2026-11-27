# Clean Architecture plan

Two linked efforts, tracked in Linear:

- **PL-1709**, the tool: `oo-ratchet` drives Clean Architecture in the repos
  that adopt it.
- **PL-1710**, this repo: `oo_ratchet` itself moves to Clean Architecture,
  as the first adopter of every PL-1709 feature.

This follows PL-1685 (PR #27). That change stopped the OO gate pushing code
into tiny one-class modules, and made a branch be judged against the merge
base.

## The target model

Four rings. Imports point only inward, and the domain imports no IO.

| Ring | Holds | May import |
|------|-------|------------|
| `domain` | metric values, rules, baseline rows, reviews and verdicts, design findings, audit records | nothing outside the domain; no `subprocess`, `os`, `pathlib`, `json`, sockets |
| `application` | the operations (`Check`, `Update`, `Relax`, `RebaselineFiles`, `Rebaseline`), written once for every gate; the ports as `Protocol`s (`History`, `BaselineStore`, `AuditSink`, `SourceReader`); `GatePolicy` | `domain` |
| `adapters` | `GitRepo` (implements `History`), the JSON baseline and audit files, config readers, report rendering | `application`, `domain` |
| `entry` | `__main__`, each gate's CLI, wiring each gate's adapters to its operations | everything |

Each gate is a vertical slice through the rings:

- **domain:** its scorer and rules;
- **application:** its comparison policy;
- **adapters:** its baseline format.

| Gate | Policy |
|------|--------|
| `oo` | must improve, no regression |
| `coupling` | no regression |
| `suppression` | the total may not rise |
| clean `layers` | violations may only shrink |
| `design` | advisory: reports new findings against the merge base |

The **clean layers ratchet** enforces the model, on adopters and on this repo:

- **DependencyRule:** imports point inward.
- **DomainPurity:** the domain imports no IO. This promotes today's advisory
  `domain-io` rule into a gate.
- **The baseline may only shrink** against the merge base.

![Target: four rings by gate](architecture/3-target-clean-architecture.png)

## Starting point (main at c825334)

Measured with this repo's own tool:

![Current packages and classes](architecture/1-current-state.png)

- **Imports:** one cycle between modules (`package_graph.py`):
  `source_archive` imports the `ArchiveRepo` protocol from `source_rescan`
  under `TYPE_CHECKING`, and `source_rescan` imports `SourceArchive` at run
  time. Moving that protocol into the application ring as a port (A2) removes
  it. Between packages there are no cycles
  once the root package's entry modules (`__main__`, `gates`) are counted
  apart from its shared modules (`source_set`, `backfill`, ...). Counted as one
  root package, every package sits in one cycle: `gates` imports each gate's
  `cli`, and every gate imports `source_set`. The entry ring in the target
  removes that cycle. The dependency graph runs
  `entry → layers → design → oo/coupling → core`. The largest
  edge is `layers → design`, with 22 imports: the layers gate runs on code
  that lives in the advisory design package.
- **Duplication:** 7 class names are defined in more than one gate: `GitRepo`
  (in `oo`, `coupling` and `suppression`), `Cli`, `Options`, `Outcome`,
  `Diff`, `GitError`, `Row`. There are three audit logs, each with a
  9-parameter `append`.
- **OO gate:** 1 module of 131 fails a target: complexity 12 in
  `coupling/metrics.py`.
- **Coupling gate:** 6 files over a cap: the two package `__init__` export
  files, `coupling/cli.py`, the two `gitio.py` classes, and
  `design/class_rules.py`.
- **Suppressions:** 19.
- **Design check:** 153 advisory findings. 43 `primitive-params`, 40
  `concrete-cross-package-import`, 24 `data-clump`, 13 `feature-envy`, 13
  hollow classes (8 function bags, 5 single-method classes), 10 `size-cap`,
  and 10 others.

### Ring counts

The four-ring table for `src/oo_ratchet` is the `[tool.oo-ratchet.layers]` table in `pyproject.toml`.
Modules are placed by role; the table lists every pattern and module it names.
The main ones: `*.gitio`, `*.baseline`, `*.audit`, `*.report`, `*.outcome`,
config readers such as `coupling/config` and the `source_*` modules are
adapters; `*.ratchet`, `*.compare`, `*.bless`, `*.relax`, `*.writer`, `*.rescan`,
`*.apply`, `*.scan`, the `shadow*` modules, `backfill` are application; `__main__`, `gates`, `usage`,
`logging_config` and `*.cli` are entry; every module the table does not name is
domain. The counts below were measured on the `src/oo_ratchet` of main 987f57b
with the table of `docs/architecture/four-rings.toml` as added in b4b85a5
(137 files scanned, 243 findings). Reproduce them: extract `src` of 987f57b
(`git archive 987f57b src`), save `git show b4b85a5:docs/architecture/four-rings.toml`
to a file and run `uv run oo-ratchet design src/oo_ratchet/ --layers <that file> --json`.
The current tree, with the table in `pyproject.toml`, is measured by
`uv run oo-ratchet design src/oo_ratchet/ --json` from the repository root:
139 files scanned, 248 findings; `layer-import` 130, `domain-io` 9,
`thick-entry` 9.

| Rule | Count |
|------|-------|
| `layer-import` | 130 |
| `concrete-cross-package-import` | 40 |
| `size-cap` | 10 |
| `domain-io` | 9 |
| `primitive-params` | 9 |
| `stateless-function-bag` | 8 |
| `feature-envy` | 7 |
| `stateless-single-method` | 5 |
| `getter-heavy` | 3 |
| `split-cohesion` | 3 |
| `middle-man` | 2 |
| `envied-data` | 1 |
| `thick-entry` | 9 |
| `data-clump` | 6 |
| `tag-switch` | 1 |
| `unlayered-module`, `misplaced-function` | 0 |

The 130 `layer-import` violations by importing ring and the ring imported:

| From | Imports | Count |
|------|---------|-------|
| domain | adapters | 42 |
| domain | entry | 12 |
| domain | application | 21 |
| application | adapters | 55 |

Entry and adapters import nothing outward. 54 of the 130 are in the four package
`__init__.py` files (`oo`, `coupling`, `layers`, `suppression`), which are
domain by the table and import the modules they export, most of them in the
outer rings. The most
imported outer modules are `source_set` (17), `coupling/outcome` (7),
`oo/baseline` (7), `coupling/gitio` (6), `oo/compare` (6), `oo/audit` (6) and
`oo/gitio` (6).

The 9 `thick-entry` findings are methods of the four CLI modules (`oo`, `coupling`,
`suppression`, `layers`) whose complexity exceeds 4 (`oo/cli.py` `Cli._run_action` is 10). The 9 `domain-io`
findings are in 8 modules: 6 import `pathlib`
(`coupling/packages`, `coupling/scorer`, `design/layer_table`,
`design/modules`, `oo/scorer`, `suppression/scanner`), 2 import `io`
(`oo/code_lines`, `suppression/patterns`) and `oo/scorer` also imports `json`.

With layers configured, `primitive-params` applies only to domain modules
(9, against 43 without layers), `feature-envy` is 7 (13 without) and
`data-clump` is 6 (24 without), because entry and adapter modules are
excluded.

`adopter_shape.py src/oo_ratchet` reports, without layers: 131 modules
(excluding `__init__`), module size median 62 (p25 38, p75 98, max 256), 36
modules of at most 40 code lines, 0 over the 400-line ceiling, and classes per
module of 0 (10 modules), 1 (116) and 2 (5).

An intermediate target, gates above one shared core, came before the ring
form. It is kept for comparison:

![Intermediate target: gates above a shared core](architecture/2-target-layered.png)

## Units

**PL-1709, the tool:**

| Unit | Linear | What |
|------|--------|------|
| B1 | PL-1711 | clean layers ratchet: DomainPurity enforced, four rings as the documented default |
| B2 | PL-1713 | `layers --suggest`: a starter ring table built from each module's imports |
| B3 | PL-1715 | design rules scoped by ring |
| B4 | PL-1716 | measure design-rule precision on vox, quarry, lux and z-spec; gate the rules that are right ≥ ~90% of the time |
| B5 | PL-1712 | average complexity and average params become ceilings |
| B6 | PL-1714 | `layers --json` adds each module's ring and the edges between rings, for diagrams |
| B7 | PL-1717 | release 0.7.0, adoption guide, rollout to the adopter repos |

**PL-1710, this repo:**

| Unit | Linear | What |
|------|--------|------|
| A0 | PL-1718 | measure: write the four-ring table, record the starting counts |
| A1 | PL-1719 | turn on the clean layers ratchet here, with today's violations as the baseline |
| A2 | PL-1720 | shared contract: ports, domain types, operations written once, one adapter set; `ArchiveRepo` becomes a port, ending the one module cycle |
| A3 | PL-1721 | move each gate onto the contract: `suppression` first, then the rest in parallel |
| A4 | PL-1722 | class debt: split `SourceSet`, `MetricRule` objects, fold the hollow classes, objects decide for themselves |
| A5 | PL-1723 | method and signature debt: feature envy, complexity, long signatures, data clumps |

### A2 decisions

The shared core lives in `src/oo_ratchet/core/` with `domain/`, `application/`
and `adapters/`. The layers table in `pyproject.toml` names each ring. The
glob `oo_ratchet.*.baseline` matches across dots, so a core module is never
named after an existing ring pattern (`audit`, `baseline`, `report`, `cli`).

- **Domain types are frozen data.** `Score`, `BaselineRow`, `Measurement`,
  `Metric`, `Waiver`, `FileReview`, `Review`, `Failure`, `Verdict`,
  `AuditRecord`, `Diff` (renames as a dict), `SourceSelection` (strings, no
  `Path`) and `StateError`/`GitError`. The domain imports no IO module.
- **A baseline is `Rows`**, `{path: {metric: number}}`, the shape the OO and
  coupling gates already write. Gate-specific metric sets differ only in the
  `GatePolicy` table.
- **`GatePolicy` holds the differences between gates**: the metric table
  (target, direction, ceiling) and three flags. `must_improve` (OO true,
  coupling false), `absolute_targets` (a new file or a metric missing from the
  base row is judged by its target; OO true, coupling reports it as info) and
  `lock_rows` (the in-tree baseline must equal the scores of every touched or
  rewritten file; OO true, coupling false).
- **Four ports plus `ArchiveRepo`.** `History` has five methods (`resolve`,
  `baseline_at`, `audit_at`, `changes_since`, `head`), `BaselineStore` three,
  `AuditSink` two, `SourceReader` three (`measure`, `exists`, `key`).
  `ArchiveRepo` moved from `source_rescan` into `core.application.ports`;
  `source_archive` and `source_rescan` import it under `TYPE_CHECKING`, which
  ends the one module cycle. It keeps its private `_git` member until A3
  deletes the three `GitRepo` copies.
- **Operations return a `Verdict`, not text.** A failure is a `Failure(kind,
  subjects)`; `GateCli` maps kinds to messages. `Check`, `Update`, `Relax`,
  `RebaselineFiles` and `Rebaseline` take a `GatePolicy` and a `Ports` bundle.
- **The CI-write guard is an adapter concern.** `GateCli.write_blocked` reads
  `GITHUB_ACTIONS`; the operations never read the environment.
- **Audit waivers come from `AuditRecord.waivers_since`**: records the base log
  does not already carry, with verdict `relaxed` or `rebaseline-files`, matched
  by a key that ignores key order.
- **Path spellings** for `RebaselineFiles` are normalised by
  `SourceReader.key`, implemented by `SourceTree`.
- **One `GitRepo` adapter** (`core/adapters/gitrepo.py`) is built from the two
  file names of a gate. It reads the baseline and audit blobs through
  `BaselineFormat` and `AuditFormat`.
- **Not in A2, left to A3:** `reconcile` (the whole-tree sweep), the
  suppression gate's total-and-ceiling-ledger comparison and its different
  audit and baseline formats, `PyprojectConfig` reading each gate's own table,
  and the `LayerModel` move out of `design` (`LayerConfig`, `Edge`,
  `Violation`, `ModuleIndex`), which touches 38 imports from `layers`.
- **Differences from the live gates, to pin as A3 equivalence cases.** No gate
  runs on the core yet; each A3 unit ports one gate behind a test that runs the
  old gate and the core on the same repository. The cases known now:
  a malformed in-tree baseline at the adoption merge (the old OO gate fails,
  `Bases.undocumented` passes); a coupling update that beats the merge base but
  loosens a tighter in-tree row (the coupling writer refuses, `PlanApplier`
  accepts); `RebaselineFiles` over-cap tests use in-tree rows, coupling bless
  uses the committed predecessor's row; bless paths given relative to the
  working directory, not the repository root; `PyprojectConfig.table` on a
  scalar parent key returns nothing where a direct query raises. The
  equivalence tests build the core's ports from the legacy adapter; A3 points
  them at `core/adapters/gitrepo.py`.
- **Tests.** `tests/core/` runs the operations against in-memory ports in
  under a second. `tests/core_real/` holds the real-git `GitRepo` tests and
  the equivalence tests: each scenario runs the existing OO gate through
  `oo_ratchet.oo.cli.main` and the new operations on the same repository, and
  the verdicts must match.

### A3 decisions: `suppression` (PL-1721)

The suppression gate compares one total, not per-file metrics, so it has its
own set of types beside the per-file ones. The CLI flags, exit codes, report
text and the three state files are unchanged.

- **Domain:** `Tally` (counts per category and per file), `TallyRecord` (one
  audited write), `Ledger` and `Ceiling` (the `.suppression-relax.json`
  ceilings; `Ledger.surviving` drops the entries the base ledger already
  carries), `TotalReview` (base total, current total, what ceilings waive, the
  files with an unwaived rise) and `TallyVerdict` (a `Verdict` plus the review
  or the record).
- **Application:** `TallyCheck`, `TallyUpdate`, `TallyRelax` and
  `TallyRebaseline` over four ports (`TallyHistory`, `TallyStore`,
  `LedgerStore`, `TallyAudit`). The operations take the measured `Tally`; they
  have no source port. `Bases` now takes two narrow protocols (`Adoption`,
  `Presence`) so both gate kinds share it; `History` gained `adopted_at`.
- **Adapters:** `TallyRepo` counts the source at a commit (`git archive` plus
  the gate's scanner), `JsonTallyStore`, `JsonLedger`, `TallyAuditFile`,
  `TallyCli` (renders a `TallyVerdict`) and `TallyGate` (builds the ports and
  runs an operation). `GitRepo` gained `exists_at` and `archive_paths`; the
  suppression `GitRepo`, `BaseRescanner`, `SuppressionBaseline`,
  `BaselineFile`, `SuppressionRelax` and `Outcome` are deleted.
- **Not moved yet:** `SuppressionReport` and `Scanner` keep their own
  by-category and by-file dicts and their own `rebased`; `Cli` converts a
  report to a `Tally`. They move with the scanner.
- **Proof:** `tests/core_real/test_suppression_gate.py` pins stdout, exit codes
  and state files. Its expected values were checked against the old gate: the
  same 18 scenarios ran through both implementations before the old one was
  deleted, and the final file also passes on the old code.
- **Known difference:** the committed `.oo-coupling-baseline.json` row for
  `suppression/__init__.py` said `efferent_coupling` 0; the file measured 8 at
  the merge base. The row was blessed (audited) at 5.

### A3 decisions: `coupling` (PL-1721)

The coupling gate runs the shared operations (`Check`, `Update`, `Relax`,
`RebaselineFiles`, `Rebaseline`). The CLI flags, exit codes, report text and
the two state files are unchanged, except the wording of a state error (below).

- **`GatePolicy` grew three flags and a table.** `in_tree_only`: an update is
  compared with the in-tree rows alone, never reads the merge-base baseline,
  and counts every file it writes a delta for as improved (a new file too).
  `detailed_refusals`: a refused bless names each metric's value and the target
  it broke. `targets` (`PathTargets`): per-file targets, a suffix rule
  (`__main__.py` gets `public_names <= 100`, `efferent_coupling <= 15`) and
  exact-path caps from `[tool.oo-ratchet.coupling.caps]`; `GatePolicy.for_path`
  returns the policy a file is judged by. `_worse` treats a metric missing from
  the recorded row as not worse when `absolute_targets` is false.
- **`RebaselineFiles` takes a `BlessBase`**: the baseline at the comparison
  base and its renames. A file is judged by its row there, a renamed file's old
  row is dropped, and a path named twice is written once. Without a base the
  in-tree rows stand in, as before. `BlessBase.load` returns the refusal for an
  unresolvable `--base-ref`, an unresolvable base under `--require-base`, or an
  empty base baseline under `--require-base`.
- **`Rebaseline` takes `reason` and `detail`.** With `detail` the audit record
  carries each changed metric as `[old, new]`, the files that gained and lost
  (`RowChanges`) and the stripped reason. Without it the record is as before.
- **Adapters:** `MetricGate` (one object per CLI run: the five operations,
  `--log`, report text through `CouplingView`), `ScoredTree` (the tree the CLI
  scored once, resolving a bless path as the repository root, the working
  directory or an absolute path), `CouplingAuditFormat` (the audit line the
  adopters hold: `reason` always present, `removed` only when non-empty),
  `AuditView` (`--log`). `coupling/gateinput.py` turns a scorer and a config
  into the core's `Measurement` and `GatePolicy`.
- **Deleted:** coupling `audit`, `baseline`, `bless`, `compare`, `delta`,
  `ratchet`, `writer`, and `GitRepo.show_baseline` / `show_audit`.
  `coupling/gitio.py` and `outcome.py` stay: `layers` and `design` still use
  them, and the `layers` port deletes them.
- **Proof:** `tests/core_real/test_coupling_gate.py` plays 68 scripted
  scenarios (`coupling_scenarios.py`) through the CLI on real git repositories
  and compares exit code, report lines, baseline text and audit lines with
  `golden_coupling_gate.json`, recorded from the gate before it moved. While
  both ran side by side, every transcript was equal.
- **Known differences:** (1) a corrupt baseline or audit log names the file
  format the core uses ("unreadable baseline ...") where the gate named
  "coupling baseline file/blob"; exit code and state files are the same, and
  the scenarios compare only the single `FAIL:` line. (2) A base baseline that
  is malformed but present at the origin/main tip reads as "base commit
  predates baseline adoption" (exit 1) where the gate raised the corruption
  error (exit 1). (3) An audit entry whose `verdict` or `deltas` has the wrong
  type waives nothing; the gate crashed on a non-string verdict. (4) A
  malformed in-tree baseline is read when the CLI starts, for every action, as
  the gate did, so the adoption-merge case fails closed.

### A3 decisions: `oo` (PL-1721)

The OO gate runs on the A2 operations. CLI flags, exit codes, report text and
both state files are unchanged.

- **Adapters:** `OoGate` (routes one command line, renders, guards CI writes),
  `OoCli` (verdict to report lines, in the old wording), `OoTree` (the scored
  tree as a `SourceReader`, with the old path-spelling lookup), `OoBaselineStore`
  (names the file in its errors, as the old gate did) and `Requested` (the
  read-only view of parsed options). `OoGate` takes the `Scorer` class and the
  `GatePolicy` from `oo/cli.py`, so no core module imports `oo`.
- **Application:** `Reconcile` (the whole-tree sweep, built on `PlanApplier`)
  and `OoRebaselineFiles` (a refusal names each metric's value and target).
- **Deleted:** `oo/ratchet`, `writer`, `apply`, `bless`, `audit`, `outcome`;
  `oo/baseline` and `oo/gitio` shrink to what the design `--shadow-check`
  still imports (`metrics_by_file`; refs, merge base, diff). `oo/compare` and
  `oo/diffmodel` stay for the same reason. They go with the design port.
- **Differences found and handled:** an audit entry whose `deltas` is not
  `{path: {metric: ...}}` waived nothing in the old gate; the core read a list
  as waiving. `AuditFormat` now drops such entries. A bless refusal, bless path
  spellings (working-directory relative) and a corrupt in-tree baseline failing
  every command are kept as before.
- **Differences left:** a corrupt baseline blob at the base reads
  `non-dict entry in baseline <ref>:<file>` (the old text added `blob at`), and
  a non-object audit line reads `not an object`. Both still exit 1 with `FAIL`.
- **Proof:** `tests/core_real/test_oo_gate.py` runs 75 invocations against
  `oo_gate_golden.json`, the old gate's recorded exit codes, stdout and state
  files. Commit b3fd2f7 ran 74 of them through both implementations.

## Order

| Wave | In parallel | Waits on |
|------|-------------|----------|
| 1 | B1, A0, B5 | — |
| 2 | A1, B2, B6 | B1, A0 |
| 3 | A2 | A1 |
| 4 | A3 (`suppression` first, then `oo`, `coupling`, `layers`, `design`), B3 | A2; B3 waits on B1 |
| 5 | A4, A5, B4 | A3, B3 |
| 6 | B7 | PL-1710 done, B2, B4, B6 |

Each unit gets its own worktree. It takes at most 3 hours (1 for the small
ones), and its first commit comes within 30 minutes. That commit is a test
that fails on the old behavior.

Each unit's PR proves itself:

- `make check` is green;
- this repo's self-gates pass against the merge base;
- the clean layers count is lower (from A1 on);
- the vox demo is unchanged.

## Done when

- The clean layers ratchet reports 0 violations on this repo.
- No class name is defined in more than one gate.
- Design findings are down from 153, with each rule's count recorded.
- vox, quarry, lux and z-spec run the clean layers ratchet with their own
  baselines.

## Decisions (recommendations)

1. `layers --suggest` writes a starter table for a person to correct. It is
   never applied automatically, because a wrong ring silently passes bad
   imports.
2. Adapters are exempt from the hollow-class rules. A thin adapter around one
   git command is correct design.
3. Adopters start from their own baseline and shrink at their own pace. This
   repo goes to zero.

## Diagrams

The PNGs above are lux screenshots. Each was drawn with a single `draw`
element (ImGui draw-list primitives) through lux's `scene_show` tool. The
generators are in `docs/architecture/tools/`:

| Script | Draws |
|--------|-------|
| `layers_diagram.py <repo> <out.json> [package-dir]` | the current state in the four rings, from `oo-ratchet layers --json` alone (`module_rings`, `ring_edges`, `marked_violations`); run from the repo root, it uses the pyproject `[tool.oo-ratchet.layers]` table; an optional third argument names the package directory (default `src/oo_ratchet`); rerun after each unit |
| `class_diagram.py <repo> <out.json>` | the older current-state view: packages and key classes, from an ad-hoc import scan and `oo-ratchet design --json` |
| `target_diagram.py <out.json>` | the intermediate target (hand-specified) |
| `clean_diagram.py <out.json>` | the four-ring target (hand-specified) |
| `package_graph.py <repo>/src/oo_ratchet [--one-root]` | prints the package import edges, then every package cycle and every module cycle (strongly connected components, `TYPE_CHECKING` imports included); `--one-root` groups the entry modules with the shared root modules. `test_graph_tools.py` tests the cycle finder (`uv run pytest docs/architecture/tools/test_graph_tools.py`) |

Three measurement scripts sit beside them:

| Script | Measures |
|--------|----------|
| `demo_targets.py <adopter> <src> <main-checkout> <branch-checkout>` | the vox demo: modules, across the whole tree, that miss an absolute OO target (the targets a new file must meet), `main`'s build versus a branch's (runs `uvx --from <checkout> oo-ratchet` with the adopter as the working directory) |
| `adopter_shape.py <src>` | module size distribution, classes per module, and design finding counts (run with `uv run --directory <repo> python ...`) |
| `compare_checks.py <repo>` | the OO gate and the design check on each `evals/design` bad/good pair |

All three read the gate through `oo_json.py`. It runs `oo-ratchet --json`, stops
with a message when the command is missing, prints no JSON, or cannot score a
file, and checks each value against the target that run reported.

The four diagram scripts each write one lux `draw` element as JSON;
`package_graph.py` and the measurement scripts above print plain text. To
show a diagram:

1. Wrap it in a lux render request:
   `{"scene_id": "<id>", "elements": [<element>], "title": "<title>",
   "frame": {"size": [1500, 840]}}`.
2. Run `lux display start`, then `lux scene show <id> --from request.json`.
3. Capture the image with lux's `display_screenshot` tool.

Run `layers_diagram.py` and `class_diagram.py` with
`uv run --directory <repo> python ...`, because they call `oo-ratchet`.

`layers --json` counts one edge per pair of importing and imported module. The
design check's `layer-import` rule counts one finding per import site, so its
totals are larger. With the table in `pyproject.toml`, `layers --json` reports
application to adapters 50, domain to adapters 29, domain to application 14 and
domain to entry 4: 97 layer edges, plus 9 domain-purity (`io`) edges, 106 in
all, the number of baselined edges `make check-layers` reports.
