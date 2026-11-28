# Reference

The detailed specification of every gate: targets, counting rules,
updates and exceptions, file formats, namespace workspaces, diagnostics, and
what the gates do not measure. For setup, see
[Configuring a Repo](CONFIGURING.md). The `layers` gate is in
[LAYERS.md](LAYERS.md) and the `design` check in [DESIGN.md](DESIGN.md).

**Contents**

- [Targets and Counting Rules](#targets-and-counting-rules)
- [Updating and Making Exceptions](#updating-and-making-exceptions)
- [Baseline and Audit Formats](#baseline-and-audit-formats)
- [Namespace Workspaces](#namespace-workspaces)
- [Diagnostics and Usage Telemetry](#diagnostics-and-usage-telemetry)
- [What the Ratchet Measures and Does Not](#what-the-ratchet-measures-and-does-not)
- [Provenance](#provenance)

## Targets and Counting Rules

The OO targets are fixed in
[`oo/thresholds.py`](../src/oo_ratchet/oo/thresholds.py), not configurable.
These are absolute targets for new files, not permission to regress an
existing file that is already below a cap. Existing debt may remain unchanged
or improve; `--update` never loosens a recorded metric, even within a cap,
except the ceiling metrics `module_size`, `avg_params` and `avg_complexity` under their targets (below).

| OO baseline field | Target | Computation |
|-------------------|--------|-------------|
| `encapsulation_ratio` | >= 1.0 | Private `self` attribute assignments / all such assignments; 1 if none |
| `avg_params` | <= 4.0, ceiling | Mean parameter count over every `def` / `async def` |
| `max_complexity` | <= 10 | Maximum function cyclomatic complexity; 0 if no functions |
| `avg_complexity` | <= 5.0, ceiling | Mean function cyclomatic complexity; 0 if no functions |
| `module_size` | <= 400, ceiling | Physical lines carrying code tokens, excluding docstrings |
| `init_violations` | == 0 | Explicit synchronous `__init__` methods on non-dataclass classes |
| `public_attr_violations` | == 0 | Assignments to `self` attributes not starting with `_` |
| `future_annotations` | == 1 | Presence of `from __future__ import annotations` |

`module_size`, `avg_params` and `avg_complexity` are ceilings, not ratcheted
values. Under its target (400 code lines, 4.0 parameters, 5.0 complexity), a
metric may rise without a regression and falling is not an improvement; over
its target, any rise regresses and any fall improves. Comparing module size
file by file rewarded splitting cohesive code into tiny modules; comparing the
averages punished deleting trivial functions or adding real decisions.

Module shape is not gated. `--json` still reports `method_ratio`,
`class_to_func_ratio` and `classes_per_module` per file, but no target applies
to them and baselines do not record them: requiring classes over functions and
few classes per module pushed code into one-class modules and functions
wrapped in stateless classes. The advisory `design` check reports those shapes
directly (`stateless-single-method`, `stateless-function-bag`), along with
responsibility problems such as `envied-data` and `feature-envy`. Those
findings measure design better than module size or shape does. Their precision
on adopter repositories is measured (see [Shadow Design Ratchet](DESIGN.md#shadow-design-ratchet)): only
`stateless-single-method` is gate-capable; `stateless-function-bag` is 67%.

Parameter counts include positional-only, ordinary and keyword-only arguments,
exclude `*args` / `**kwargs`, and subtract a leading `self` or `cls`; no
functions gives 0. Complexity starts at 1 and adds one for each `if`, ternary,
`while`, `for`, `async for`, exception handler and `assert`; each boolean or
or-pattern alternative after the first; each comprehension plus its filters;
and each `case` (including `_`) plus its guard. Nested function bodies are
scored separately, not charged to the enclosing function; their headers are
still visited there. Encapsulation ratios round to 3 decimal places;
parameter and complexity averages round to 2.

Encapsulation counts assignment occurrences, not unique fields: only direct
`self.x` targets of `Assign` / `AnnAssign` are collected, not augmented,
destructuring or reflective assignments. The `__init__` exemption recognizes
`@dataclass`, `@dataclass(...)` and bare `@module.dataclass`, but not the called
qualified form `@module.dataclass(...)`.

Since 0.3.0, [`CodeLines`](../src/oo_ratchet/oo/code_lines.py) excludes blank lines,
comment-only lines, and module/class/function/async-function docstrings.
Trailing comments do not remove the code line. Non-docstring strings count,
including nonblank lines spanned by multiline strings; a docstring sharing a
line with real code does not remove that code. A physical line counts once.

[`ClassKinds`](../src/oo_ratchet/oo/class_kinds.py) excludes these from the
reported, ungated `classes_per_module` (nested classes never count):

- Bases named `Protocol` or `TypedDict`.
- Bases named `Enum`, `IntEnum`, `StrEnum`, `Flag`, `IntFlag`, `ReprEnum`,
  `Exception` or `BaseException`, or whose names end in `Error`, `Exception`
  or `Warning`; later local subclasses of these exempt classes also qualify.
- Classes decorated with `dataclass`, with or without arguments.

This is syntactic name matching, including qualified final names and
subscripted bases, not import/type resolution. Implementations of a local
Protocol and subclasses of local dataclasses are not automatically exempt.

Coupling defaults come from
[`coupling/thresholds.py`](../src/oo_ratchet/coupling/thresholds.py):

| Coupling baseline field | Default target | Computation |
|-------------------------|----------------|-------------|
| `efferent_coupling` | <= 10 | Distinct internal modules resolved from top-level imports |
| `public_names` | <= 15 | Literal list/tuple `__all__` length, else public top-level definitions and simple assignment targets |
| `circular_imports` | == 0 | 1 for a module in an internal import cycle, otherwise 0 |
| `max_lcom` | <= 0.8 | Maximum eligible class LCOM; 0 if none |
| `avg_lcom` | <= 0.5 | Mean eligible class LCOM, rounded to 3 places; 0 if none |

Paths ending in `__main__.py` instead get coupling <= 15 and public names
<= 100. All five targets can be overridden for exact repository-relative paths
using the coupling `caps` table (see
[Configuring a Repo](CONFIGURING.md#coupling-settings); even `circular_imports`,
whose configured cap becomes a `<=` comparison). There is no global OO or
suppression threshold setting. `stateless-values` configures LCOM exemptions,
not a numeric target.

[`LCOM`](../src/oo_ratchet/coupling/metrics.py) is the fraction of instance-method
pairs with disjoint sets of `self` data attributes (public or private), rounded
to 3 places. Direct `self.helper()` call targets are excluded; static and class
methods are excluded; fewer than two instance methods yields no class score.
Only top-level classes are considered. Bare/subscripted bare `Protocol`,
`TypedDict` and `BaseModel` bases are exempt, as are stateless value shapes
described in [Configuring a Repo](CONFIGURING.md#coupling-settings). Imports inside functions, classes or conditional
blocks, external dependencies, dynamic imports and runtime calls are not
coupling edges. Public-name fallback ignores imports and annotated assignments.

Suppressions has no fixed numeric cap: the allowed total is the live base-tree
total, plus active audited waivers. Categories are `noqa`, `type_ignore`,
`pylint_disable`, `pyright_ignore`, `file_level` and `per_file_ignores`.
Inline markers count once per matching category per code-line comment, not per
rule code; strings containing markers do not count. File-level directives
(ruff/flake8 noqa, mypy ignore-errors, pyright basic or report-setting false,
pylint skip-file), own-line pylint disable, and pre-code type-ignore directives
are counted separately. Ruff's `[tool.ruff.lint.per-file-ignores]` counts each
listed code for each literal pattern, not each matching file. A tokenization
failure deliberately over-counts marker-bearing lines rather than returning
zero. See [`suppression/patterns.py`](../src/oo_ratchet/suppression/patterns.py).

## Updating and Making Exceptions

Run from the repository root, using the scored file's repository-relative path
for `--relax`. Commit baseline and audit changes with the source change.

```bash
oo-ratchet oo src/pkg/ --update --source PL-123
oo-ratchet oo src/pkg/ --relax src/pkg/model.py --justify "Required API change" --source PL-123
oo-ratchet oo src/pkg/ --rebaseline-files src/pkg/model.py --reason "Required API change" --source PL-123
oo-ratchet oo src/pkg/ --check --base-ref "$(git merge-base origin/main HEAD)" --require-base
```

OO actions are mutually exclusive. The write contracts, implemented in
[`core/application/update.py`](../src/oo_ratchet/core/application/update.py),
[`core/application/reconcile.py`](../src/oo_ratchet/core/application/reconcile.py) and
[`core/application/waive.py`](../src/oo_ratchet/core/application/waive.py), are:

| Action | Allowed / refused |
|--------|-------------------|
| `--update` | Scopes to the base diff, carries rename history, removes vanished rows, writes new/non-regressing rows; refuses any metric regression against the baseline at the merge base (the in-tree baseline when the base has none) and preserves refused rows. A later commit on a branch may give back part of an earlier commit's gain while it stays no worse than the base. Parse-error rows are kept and refused. |
| `--reconcile` | Explicit whole-scored-tree never-loosening sweep, with rename carry and deletion pruning; not a reset. |
| `--relax FILE --justify TEXT` | Writes all current metrics for an already-baselined scored file, even over target. Refuses blank justification, unscored files, new files, or a file with no actual regression. Audits only loosened metrics as waiver deltas. |
| `--rebaseline-files PATH[,PATH...] --reason TEXT` | Bounded bless of only named scored files; refuses blank reason or an empty path list. A metric blocks its file only if both outside target and worse than its prior baseline. Unchanged/improved over-target debt carries; without a prior metric, outside target refuses. Accepted files are written even if others refuse (exit 1). |
| `--rebaseline` | Unconditional structural reset to the parse-clean current snapshot, dropping other rows. Can loosen; audited, but unlike relax/bless does not itself grant a check-time regression waiver. No reason is required by the OO implementation. |

All OO writes refuse when `GITHUB_ACTIONS=true` unless `--allow-ci-write` is
passed. Scoped update refuses an unresolved base when a baseline exists (or
`--require-base` is set); only first adoption without an in-tree baseline may
bootstrap the whole scored tree. Reconcile also needs a resolvable default base
when a baseline exists, to preserve rename provenance. `--source` is optional
audit metadata (for example a PR/bead reference), not authorization;
`--justify` belongs to relax and `--reason` to the bounded bless.

OO `--check` requires touched-file baseline values to equal current scores.
It compares those scores against the baseline committed at the merge base,
never against an intermediate commit on the branch, follows renames, rejects
regressions, and normally requires at least one improvement across existing
touched files. A gated metric missing from a file's base row is judged by its
target and never counts as an improvement. If all files are new, passing
their targets suffices. With no touched scored Python files, `--check`
passes once every row the branch rewrote matches the code: a file improved
and then reverted to its base contents leaves its row out of date until
`--update` refreshes it.
`--allow-no-improvement` waives only the improvement requirement, not
regressions, parse failures or baseline integrity.

Relax/bless audit entries absent from the comparison base waive only their
recorded file/metric pairs, and only while the current value is locked in the
in-tree baseline; an exercised waiver also satisfies must-improve. Historical
entries already at the base do not waive later regressions. A full reset is
therefore not a substitute for relax when a change needs a waiver.

Since 0.3.1, both OO and coupling scoped `--update` also **backfill missing rows**
for parse-clean scored files outside the diff, including untracked files in
the scored tree. Existing untouched rows are not refreshed. Rename targets
use the normal carry path, not backfill. Backfills appear as `backfilled` audit
paths, not metric deltas or improvements; successful runs print them. Updates
may still write accepted rows/backfills when another file refuses; they return
nonzero and suppress the success-only backfill output. See
[`tests/test_update_backfill.py`](../tests/test_update_backfill.py).

Both scoped `--update` runs also drop the baseline row of any file that no
longer exists in the tree, whether or not the diff names it, and report it under
`removed` (in the printed summary and the audit entry). A rename source keeps its
row until the rename target is written, and a row of an existing file that fails
to parse is kept.

Coupling is regression-only (no must-improve condition) and supports its own
relax/bless flow. Suppression `--update` refuses a static-total increase;
`--rebaseline --reason` may raise that snapshot, but does not waive a live
base-tree increase. Suppression `--relax FILE --justify TEXT` records a per-file
ceiling in `.suppression-relax.json`; only the current change can use it, and
growth beyond the ceiling is not covered.

## Baseline and Audit Formats

Files live at the repository root. `.oo-baseline.json` and
`.oo-coupling-baseline.json` are JSON objects keyed by repository-relative POSIX
file path; each newly scored value has exactly the tracked
metric fields in its table above, stored as numbers. There is no version,
timestamp, cap or justification field in these two snapshots. OO scorer-only
`file`, `top_level_functions` and `top_level_statements` are not baseline fields.
For example, one complete row in each respective file:

```json
{
  "src/pkg/model.py": {
    "encapsulation_ratio": 1.0,
    "avg_params": 1.0,
    "max_complexity": 1.0,
    "avg_complexity": 1.0,
    "module_size": 12.0,
    "init_violations": 0.0,
    "public_attr_violations": 0.0,
    "future_annotations": 1.0
  }
}
```

```json
{
  "src/pkg/model.py": {
    "efferent_coupling": 1.0,
    "public_names": 1.0,
    "circular_imports": 0.0,
    "max_lcom": 0.0,
    "avg_lcom": 0.0
  }
}
```

`.oo-audit.jsonl` and `.oo-coupling-audit.jsonl` append one JSON object per
write. Their fields are:

| Field | Meaning |
|-------|---------|
| `ts` | UTC timestamp, `YYYY-MM-DDTHH:MM:SSZ` |
| `commit` | Short HEAD SHA, or null when unavailable |
| `source` | Optional caller reference, otherwise null |
| `files_scored` | Number of parse-clean files scored |
| `files_improved` | Writer's improvement count. OO updates count files with a metric strictly better than their previous row (not new rows, backfills, or a move of a ceiling metric (`module_size`, `avg_params`, `avg_complexity`) that stays under its target); coupling updates count changed accepted rows, including new rows, not backfills |
| `files_regressed` | Writer's refused/regressed file count (updates also include parse failures); not necessarily zero for an intentional bless |
| `verdict` | Operation/result: `pass`, `fail`, `relaxed`, `rebaseline-files`, `rebaseline` |
| `reason` | Human justification; OO omits it if unset, coupling writes null |
| `deltas` | Path -> metric -> `[old, new]`; ordinary update changes, but only waived regressions for relax/bless |
| `removed` | Deleted baseline paths; always present for OO, omitted when empty for coupling |
| `improved` | Optional bless-only path/metric deltas for gains, separate from waivers |
| `backfilled` | Optional list of missing out-of-diff paths added, without implying improvement |

Example OO relax audit line (illustrative values):

```json
{"ts":"2026-01-01T00:00:00Z","commit":"abc1234","source":"PL-123","files_scored":4,"files_improved":0,"files_regressed":1,"verdict":"relaxed","reason":"Required API change","deltas":{"src/pkg/model.py":{"max_complexity":[3.0,5.0]}},"removed":[]}
```

`.suppression-baseline.json` has `total` (sum of categories), `by_category`
(all six category totals), `by_file` (only nonzero categories per source path
or literal per-file-ignore pattern), and `updated_at` (UTC timestamp).
Unlike OO/coupling snapshots, it is not the comparison source for `--check`:
both current and base source are scanned with the current counter.

```json
{
  "total": 1,
  "by_category": {"noqa": 1, "type_ignore": 0, "pylint_disable": 0, "pyright_ignore": 0, "file_level": 0, "per_file_ignores": 0},
  "by_file": {"src/pkg/model.py": {"noqa": 1}},
  "updated_at": "2026-01-01T00:00:00Z"
}
```

`.suppression-audit.jsonl` uses different records: plain updates contain `ts`,
`total`, `by_category`; relax records contain `ts`, `verdict: "relaxed"`, `file`,
`before`, `after` (file counts), `reason`, `commit`; resets contain `ts`,
`verdict: "rebaseline"`, `before` (old total or null), `total`, `by_category`,
`reason`, `source`, `commit`. Example plain update:

```json
{"ts":"2026-01-01T00:00:00Z","total":0,"by_category":{"noqa":0,"type_ignore":0,"pylint_disable":0,"pyright_ignore":0,"file_level":0,"per_file_ignores":0}}
```

`.suppression-relax.json` is a JSON array of entries with `file` (path),
`ceiling` (positive integer allowed file total), `justify` (human explanation)
and `added_at` (UTC timestamp). Re-relaxing a file replaces its entry:

```json
[{"file":"src/pkg/model.py","ceiling":2,"justify":"Upstream typing gap","added_at":"2026-01-01T00:00:00Z"}]
```

## Namespace Workspaces

All gates accept portions of one top-level namespace as a single scan:

```bash
oo-ratchet coupling --namespace punt_lux \
  packages/lux-kernel/src/punt_lux packages/lux-hub/src/punt_lux --check
oo-ratchet design --namespace punt_lux \
  packages/lux-kernel/src/punt_lux packages/lux-hub/src/punt_lux \
  --shadow-check origin/main
```

Each root is the namespace directory itself, not its parent `src` directory
or a component such as `punt_lux/kernel`. A root `__init__.py` is not required.
Portions are joined before resolving imports or measuring cycles and package
metrics; they are not independent scans. Duplicate module definitions across
portions, nonexistent roots, unmatched globs and entirely empty selections fail
before any baseline is written. Repeated identical roots are deduplicated.

Alternatively, configure the selection in the working directory's nearest
`pyproject.toml` and omit positional sources:

```toml
[tool.oo-ratchet]
namespace = "punt_lux"
roots = ["packages/*/src/punt_lux"]
```

Configured paths and globs are relative to that file. Explicit roots override
configured roots; specify `--namespace` with an explicit single root to opt in.
A single positional source without `--namespace` retains legacy behavior.
The namespace must be one top-level Python identifier.

Import identity is the namespace plus the source-relative dotted key, e.g.
`punt_lux.kernel.paths`. Internal coupling keys and design module keys retain
the legacy namespace-relative spelling (`kernel.paths`); layer edges retain
fully qualified names. Existing module-name declarations therefore need **no
rekey**. Physical-path configuration (coupling caps, suppression waivers),
baselines and audit rows retain actual repository-relative file paths. Moving
a file changes its physical key as before; `--base-ref` uses Git rename
detection to pair its old and new keys, including historical shadow and
suppression scans. List all portions of the namespace when moving a monolith
into a workspace so its before/after graph scopes are equivalent.

Historical root globs are constrained to the selected namespace name and retain
resolved physical portions. Relative symlink portions within the checkout are
deduplicated; links escaping a historical checkout fail closed. Use physical
roots rather than absolute symlinks for portable history checks. Historical
scans retain both the selected project's configuration and repository-root Ruff
ignores.

The usual `--check`, `--update`, `--base-ref` and `--require-base` flags apply
to the baseline gates; design retains its advisory `--shadow-check REF`.

## Diagnostics and Usage Telemetry

Gate reports and `--json` output go to stdout only. Diagnostics and usage
capture are two separate pipelines with separate files, both written through
the shared [`punt-observe`](https://pypi.org/project/punt-observe/) package.

### Diagnostic log

Each run appends to `~/.punt-labs/oo-ratchet/logs/oo-ratchet.log`, one line per
record: `2026-11-27 22:28:00 [INFO] oo_ratchet.usage: Finished oo gate: pass in 7 ms`.

- **Location and permissions.** The directory is `0700`; the log, its backups
  `oo-ratchet.log.1` to `.5` and the rotation lock file are `0600`. Existing
  loose files are tightened at startup. If one cannot be (a backup slot that is
  a symlink, for example), the run stops with exit 2 and
  `cannot open the diagnostic log`, and writes nothing.
- **Rotation.** 5 MiB per file, 5 backups, safe for several oo-ratchet
  processes writing at once (a lock file serializes the rollover). Total
  storage stays under 30 MiB.
- **Redaction.** Every record is redacted after formatting, including
  exception text and tracebacks: URL credentials, paths and query strings are
  masked, control characters are escaped, and a record is one physical line.
  The home directory prefix of a path becomes `~`. The rest of a path is kept
  as written, so a repository's directory names appear in the lines that name
  a baseline or audit file.
- **Levels.** INFO records a decision or a state change. WARNING records a
  refusal the caller must act on or state that could not be read. ERROR
  records an unexpected exception, with its redacted traceback. Warnings and
  errors are also echoed to stderr.
- **What a run logs.**
  - Start: `Running <gate> gate (oo-ratchet <version>)`; end:
    `Finished <gate> gate: <outcome> in <n> ms`.
  - A write that changes state: `Wrote baseline <path>: <n> files`,
    `Wrote suppression baseline <path>: <n> total`,
    `Wrote layers baseline <path>: <n> edges`,
    `Appended <verdict> entry to audit <path>` (the verdict is `pass`,
    `rebaseline-files`, `relax` and so on). `--update`, `--rebaseline`,
    `--rebaseline-files`, `--reconcile` and `--relax` all log through these.
    Counts and file names only: never a baseline row, a `--reason` or a
    `--justify` text.
  - A refusal or failed check: `Operation refused: <kind>, <kind> (<n>
    subjects)`. The kinds are the closed names the report uses, such as
    `regression`, `no-improvement`, `suppression-increase`, `base-unresolvable`
    and `ci-write`. A gate doing its job (a regression, a refused loosening)
    is INFO; a cause you can fix, such as an unresolvable base, is a WARNING.
    The subjects (file names) are counted, not listed.
  - Unreadable state: `Gate state unreadable (<ErrorType>): '<message>'`, a
    WARNING, for a corrupt baseline, an unreadable audit log, a bad
    `pyproject.toml` or a failed git command.
  - An unexpected exception: an ERROR line with the traceback, then the
    exception propagates.
  - Git degradation: a WARNING when git cannot run.
  - Nothing else: no per-file or per-iteration lines.

### Usage telemetry

Each run records one local event, `oo-ratchet.cli.<gate>` schema version 1, in
`~/.punt-labs/oo-ratchet/telemetry.db` (SQLite; the directory is `0700`, the
database and its `-wal` and `-shm` files `0600`). The schema is an allowlist of
two typed attributes: `outcome` (`pass`, `fail`, `invalid` or `error`) and
`duration_ms`. An unknown attribute, a wrong type or an unknown version drops
the event; it never fails the run. No paths, source, baselines or report text
are recorded, no identifier is hashed (so no salt file is created), and nothing
leaves the machine: oo-ratchet imports no exporter, and network export is a
`punt-observe` setting that needs its own opt-in.

- **Retention.** 90 days by default. Expired rows are deleted and the space is
  reclaimed when the database is opened at the start of the next run.
  `telemetry-retention-days = N` (1 to 3650) under `[tool.oo-ratchet]` changes
  it; a value outside the range is ignored with a WARNING and the 90-day
  default applies. Retention cannot be unlimited.
- **Off switches.** Any one of these turns capture off, and nothing is opened
  while off: no database, no sidecar files, no background thread. The diagnostic
  log is unaffected.

  | Switch | Scope |
  |--------|-------|
  | `PUNT_TELEMETRY=off` | every Punt Labs tool on the machine |
  | `OO_RATCHET_TELEMETRY=off` | oo-ratchet, from the environment |
  | `telemetry = false` under `[tool.oo-ratchet]` | one project |

  `off`, `0`, `false` and `no` all mean off in the environment variables. The
  `pyproject.toml` is the nearest one found from the current directory up to
  the repository root. A `telemetry` value that is not `true` or `false`, or a
  `pyproject.toml` that cannot be parsed, turns capture off and logs a WARNING.

## What the Ratchet Measures and Does Not

The ratchet encourages decomposition and selected OO conventions, not proof of
good OO design. Method/class ratios favor class-based organization;
encapsulation checks underscore-prefixed assignment targets, not access control
or behavioral boundaries. LCOM adds a real data-cohesion signal (shared fields
between instance methods), and internal-import counts/cycles expose structural
coupling. Size, parameter and complexity limits and suppression counts are
general Python maintainability signals, not specifically OO quality. There
are no checks of inheritance design, polymorphism, substitutability, domain
modeling or whether an abstraction has a coherent responsibility; small classes
and shared fields can still encode poor designs. Use the gates as review
prompts and regression protection, not a replacement for design review.

## Provenance

Seeded from vox (`tools/oo_ratchet`, `tools/coupling`, `tools/suppression`),
then merged:

- **quarry**: coupling `--tripwire`, `tokenize`-based suppression scan, and an
  extraction waiver for the two class-shape ratios, since removed with those
  ratios.
- **lux**: `--rebaseline-files` bounded bless with over-cap carry (`bless.py`),
  vanished-row cleanup on `--update`, removed rows recorded in the audit log;
  in 0.2.0 the broad stateless-value LCOM exemption, exact-path coupling caps
  (as `[tool.oo-ratchet.coupling]` config) and coupling `--rebaseline-files`.
- **new here**: unreadable or non-UTF-8 files become error rows instead of
  crashing the OO scorer (PL-778).
