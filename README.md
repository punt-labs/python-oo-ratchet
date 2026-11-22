# oo-ratchet

The Punt Labs quality ratchets for Python repos, extracted from the copies that
lived in `tools/` of vox, quarry, lux and z-spec. One installable package, one
CLI, three gates:

| Gate | Command | Rule |
|------|---------|------|
| OO metrics | `oo-ratchet oo <src> --check` | must-improve: no metric regresses on a touched file and at least one improves |
| Coupling/cohesion | `oo-ratchet coupling <src> --check` | regression-only |
| Suppressions | `oo-ratchet suppressions <src> --check` | regression-only on the total `noqa` / `type: ignore` / `pylint: disable` / `pyright: ignore` / per-file-ignores count |

The OO and coupling gates compare against the baseline committed at the merge
base; suppressions compares against a fresh scan of the base source tree.
The gates fail closed on unreadable comparison state and only loosen through
audited operations (`--relax`, `--rebaseline-files`, `--rebaseline`). A
suppressions `--relax` waiver covers only the change that adds it; once it
merges it is retired, so a later cleanup is a real floor. The
policy it enforces is
[`python-oo-adoption.md`](https://github.com/punt-labs/punt-kit/blob/main/lang-rules/python/python-oo-adoption.md)
in punt-kit; the formal model is [`docs/ratchet.tex`](docs/ratchet.tex).

## Install

```bash
uv add --dev punt-oo-ratchet
```

Requires Python 3.13+. No runtime dependencies.

## Use

```make
check-oo:
	uv run oo-ratchet oo src/pkg/ --check $(OO_BASE)
update-oo:
	uv run oo-ratchet oo src/pkg/ --update $(OO_BASE)
check-coupling:
	uv run oo-ratchet coupling src/pkg/ --check $(COUPLING_BASE)
check-suppressions:
	uv run oo-ratchet suppressions src/pkg/ --check $(SUPPRESSION_BASE)
```

On PRs, pass the merge-base SHA: `--base-ref "$(git merge-base origin/main HEAD)"
--require-base` (an explicit ref is compared as given, so `origin/main` itself
would pull in later main changes). On the post-merge `push: [main]` run, pass
`--base-ref HEAD~1 --require-base --tripwire` to every gate so the one-time
adoption merge bootstrap-passes. `oo-ratchet <gate> --help` lists each gate's
flags. Baseline and audit files (`.oo-baseline.json`, `.oo-audit.jsonl`,
`.oo-coupling-baseline.json`, ...) keep the same names as the embedded copies,
so a repo switches over without rebaselining.

### Advisory design check

`oo-ratchet design src/pkg/ [--json]` reports OO design smells the metric
gates cannot see: stateless classes with one public method (a function wearing
a class) or several (a namespace of free functions), getter-heavy classes, and
stateful concrete classes imported across top-level subpackages instead of a
Protocol/ABC. It has no baseline and always exits 0; it is not part of
`make check`.

**Design evals.** `evals/design/` seeds eleven library-loan bad/good pairs with
shared behavior checks and stable `(rule, path, symbol)` keys in `expected.toml`.
`tests/test_design_evals.py` checks implemented-rule recall, precision and ordering;
future-rule expectations are strict xfails, so implementing a rule forces their
promotion. Known false positives are strict xfails too, never fixture workarounds.
`make check` lints and type-checks the fixtures and runs the harness, but the
self-ratchets still scan only `src/oo_ratchet/`. The layer-leak pair's `layers.toml`
is a future layer contract, not configuration consumed by today's scanner.

## Configure

Optional per-repository settings live in `pyproject.toml`; with none the strict
defaults apply. Unknown keys, metrics or modes are an error, not ignored.

```toml
[tool.oo-ratchet.coupling]
# "dataclass" (default): LCOM skips only @dataclass / __slots__ = () classes
# that store no instance state. "any": skip every class that never writes a
# private self._* attribute (object/super()/type(self).__setattr__ count).
stateless-values = "any"

[tool.oo-ratchet.coupling.caps]
# Exact repository-relative paths; a cap replaces that metric's default target
# for that one file (here a wiring hub whose job is importing many modules).
"src/pkg/facade.py" = { efferent_coupling = 20 }
```

`oo-ratchet coupling <src> --rebaseline-files a.py,b.py --reason "<why>"` is the
coupling counterpart of the OO bless: each named file is recorded unless a
metric is both over its cap (configured caps included) and worse than its
baseline; refused files are listed and not written, and the bless is audited
and waives exactly those deltas at the next `--check`.

`oo-ratchet suppressions <src> --rebaseline --reason "<why>" [--source PL-123]`
resets the suppression baseline to the current counts. It's the one write that may
raise the total (for example after a package upgrade changes the counter), and it
is audited.

## Reference (0.3.x)

### Targets and counting rules

The OO targets are fixed in
[`oo/thresholds.py`](src/oo_ratchet/oo/thresholds.py), not configurable.
These are absolute targets for new files, not permission to regress an
existing file that is already below a cap. Existing debt may remain unchanged
or improve; `--update` never loosens a recorded metric, even within a cap.

| OO baseline field | Target | Computation |
|-------------------|--------|-------------|
| `method_ratio` | >= 0.80 | Methods / (methods + top-level functions) |
| `encapsulation_ratio` | >= 1.0 | Private `self` attribute assignments / all such assignments; 1 if none |
| `avg_params` | <= 4.0 | Mean parameter count over every `def` / `async def` |
| `max_complexity` | <= 10 | Maximum function cyclomatic complexity; 0 if no functions |
| `avg_complexity` | <= 5.0 | Mean function cyclomatic complexity; 0 if no functions |
| `module_size` | <= 300 | Physical lines carrying code tokens, excluding docstrings |
| `classes_per_module` | <= 3 | Top-level classes, with the exemptions below |
| `class_to_func_ratio` | >= 0.5 | Classes / (classes + top-level functions), with its own narrower exclusions |
| `init_violations` | == 0 | Explicit synchronous `__init__` methods on non-dataclass classes |
| `public_attr_violations` | == 0 | Assignments to `self` attributes not starting with `_` |
| `future_annotations` | == 1 | Presence of `from __future__ import annotations` |

Details from [`oo/metrics.py`](src/oo_ratchet/oo/metrics.py): methods include
direct methods of every class in the AST (including nested classes), not just
public or instance methods. There is no methods-per-class cap. Both shape
ratios return 1 when their denominator is zero, unless there are more than 5
top-level statements, when they return 0. Imports, definitions and string
expression statements do not count toward that fallback statement count.
`class_to_func_ratio` excludes only classes with bare `Protocol` / `TypedDict`
bases (also subscripted), not all the `classes_per_module` exemptions.

Parameter counts include positional-only, ordinary and keyword-only arguments,
exclude `*args` / `**kwargs`, and subtract a leading `self` or `cls`; no
functions gives 0. Complexity starts at 1 and adds one for each `if`, ternary,
`while`, `for`, `async for`, exception handler and `assert`; each boolean or
or-pattern alternative after the first; each comprehension plus its filters;
and each `case` (including `_`) plus its guard. Nested function bodies are
scored separately, not charged to the enclosing function; their headers are
still visited there. Shape/encapsulation ratios round to 3 decimal places;
parameter and complexity averages round to 2.

Encapsulation counts assignment occurrences, not unique fields: only direct
`self.x` targets of `Assign` / `AnnAssign` are collected, not augmented,
destructuring or reflective assignments. The `__init__` exemption recognizes
`@dataclass`, `@dataclass(...)` and bare `@module.dataclass`, but not the called
qualified form `@module.dataclass(...)`.

In 0.3.x, [`CodeLines`](src/oo_ratchet/oo/code_lines.py) excludes blank lines,
comment-only lines, and module/class/function/async-function docstrings.
Trailing comments do not remove the code line. Non-docstring strings count,
including nonblank lines spanned by multiline strings; a docstring sharing a
line with real code does not remove that code. A physical line counts once.

[`ClassKinds`](src/oo_ratchet/oo/class_kinds.py) excludes these from
`classes_per_module` (nested classes never count):

- Bases named `Protocol` or `TypedDict`.
- Bases named `Enum`, `IntEnum`, `StrEnum`, `Flag`, `IntFlag`, `ReprEnum`,
  `Exception` or `BaseException`, or whose names end in `Error`, `Exception`
  or `Warning`; later local subclasses of these exempt classes also qualify.
- Classes decorated with `dataclass`, with or without arguments.

This is syntactic name matching, including qualified final names and
subscripted bases, not import/type resolution. Implementations of a local
Protocol and subclasses of local dataclasses are not automatically exempt.

Coupling defaults come from
[`coupling/thresholds.py`](src/oo_ratchet/coupling/thresholds.py):

| Coupling baseline field | Default target | Computation |
|-------------------------|----------------|-------------|
| `efferent_coupling` | <= 10 | Distinct internal modules resolved from top-level imports |
| `public_names` | <= 15 | Literal list/tuple `__all__` length, else public top-level definitions and simple assignment targets |
| `circular_imports` | == 0 | 1 for a module in an internal import cycle, otherwise 0 |
| `max_lcom` | <= 0.8 | Maximum eligible class LCOM; 0 if none |
| `avg_lcom` | <= 0.5 | Mean eligible class LCOM, rounded to 3 places; 0 if none |

Paths ending in `__main__.py` instead get coupling <= 15 and public names
<= 100. All five targets can be overridden for exact repository-relative paths
using the coupling `caps` table under **Configure** (even `circular_imports`,
whose configured cap becomes a `<=` comparison). There is no global OO or
suppression threshold setting. `stateless-values` configures LCOM exemptions,
not a numeric target.

[`LCOM`](src/oo_ratchet/coupling/metrics.py) is the fraction of instance-method
pairs with disjoint sets of `self` data attributes (public or private), rounded
to 3 places. Direct `self.helper()` call targets are excluded; static and class
methods are excluded; fewer than two instance methods yields no class score.
Only top-level classes are considered. Bare/subscripted bare `Protocol`,
`TypedDict` and `BaseModel` bases are exempt, as are stateless value shapes
described under **Configure**. Imports inside functions, classes or conditional
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
zero. See [`suppression/patterns.py`](src/oo_ratchet/suppression/patterns.py).

### Updating and making exceptions

Run from the repository root, using the scored file's repository-relative path
for `--relax`. Commit baseline and audit changes with the source change.

```bash
oo-ratchet oo src/pkg/ --update --source PL-123
oo-ratchet oo src/pkg/ --relax src/pkg/model.py --justify "Required API change" --source PL-123
oo-ratchet oo src/pkg/ --rebaseline-files src/pkg/model.py --reason "Required API change" --source PL-123
oo-ratchet oo src/pkg/ --check --base-ref "$(git merge-base origin/main HEAD)" --require-base
```

OO actions are mutually exclusive. The write contracts in
[`oo/writer.py`](src/oo_ratchet/oo/writer.py) and
[`oo/bless.py`](src/oo_ratchet/oo/bless.py) are:

| Action | Allowed / refused |
|--------|-------------------|
| `--update` | Scopes to the base diff, carries rename history, removes vanished rows, writes new/non-regressing rows; refuses any metric regression against the in-tree baseline and preserves refused rows. Parse-error rows are kept and refused. |
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
It compares those scores against the base baseline, follows renames, rejects
regressions, and normally requires at least one improvement across existing
touched files. If all files are new, passing their targets suffices. New
zero-class extractions proven to originate in baselined code may waive only
`method_ratio` and `class_to_func_ratio`. No touched scored Python files is a
trivial pass. `--allow-no-improvement` waives only the improvement requirement,
not regressions, parse failures or baseline integrity.

Relax/bless audit entries absent from the comparison base waive only their
recorded file/metric pairs, and only while the current value is locked in the
in-tree baseline; an exercised waiver also satisfies must-improve. Historical
entries already at the base do not waive later regressions. A full reset is
therefore not a substitute for relax when a change needs a waiver.

In 0.3.x, both OO and coupling scoped `--update` also **backfill missing rows**
for parse-clean scored files outside the diff, including untracked files in
the scored tree. Existing untouched rows are not refreshed. Rename targets
use the normal carry path, not backfill. Backfills appear as `backfilled` audit
paths, not metric deltas or improvements; successful runs print them. Updates
may still write accepted rows/backfills when another file refuses; they return
nonzero and suppress the success-only backfill output. See
[`tests/test_update_backfill.py`](tests/test_update_backfill.py).

Coupling is regression-only (no must-improve condition) and supports its own
relax/bless flow. Suppression `--update` refuses a static-total increase;
`--rebaseline --reason` may raise that snapshot, but does not waive a live
base-tree increase. Suppression `--relax FILE --justify TEXT` records a per-file
ceiling in `.suppression-relax.json`; only the current change can use it, and
growth beyond the ceiling is not covered.

### Baseline and audit formats

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
    "method_ratio": 1.0,
    "encapsulation_ratio": 1.0,
    "avg_params": 1.0,
    "max_complexity": 1.0,
    "avg_complexity": 1.0,
    "module_size": 12.0,
    "classes_per_module": 1.0,
    "class_to_func_ratio": 1.0,
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
| `files_improved` | Writer's improvement count; ordinary updates count changed accepted rows, including new rows, not backfills |
| `files_regressed` | Writer's refused/regressed file count (updates also include parse failures); not necessarily zero for an intentional bless |
| `verdict` | Operation/result: `pass`, `fail`, `relaxed`, `rebaseline-files`, `rebaseline` |
| `reason` | Human justification; OO omits it if unset, coupling writes null |
| `deltas` | Path -> metric -> `[old, new]`; ordinary update changes, but only waived regressions for relax/bless |
| `removed` | Deleted baseline paths; always present for OO, omitted when empty for coupling |
| `improved` | Optional bless-only path/metric deltas for gains, separate from waivers |
| `backfilled` | Optional list of missing out-of-diff paths added, without implying improvement |

Example OO relax audit line (illustrative values):

```json
{"ts":"2026-01-01T00:00:00Z","commit":"abc1234","source":"PL-123","files_scored":4,"files_improved":0,"files_regressed":1,"verdict":"relaxed","reason":"Required API change","deltas":{"src/pkg/model.py":{"avg_params":[1.0,2.0]}},"removed":[]}
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

### What the ratchet measures (and doesn't)

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

- **quarry**: extraction provenance for new zero-class modules (`diffmodel.py`,
  `provenance.py`), coupling `--tripwire`, `tokenize`-based suppression scan.
- **lux**: `--rebaseline-files` bounded bless with over-cap carry (`bless.py`),
  vanished-row cleanup on `--update`, removed rows recorded in the audit log;
  in 0.2.0 the broad stateless-value LCOM exemption, exact-path coupling caps
  (as `[tool.oo-ratchet.coupling]` config) and coupling `--rebaseline-files`.
- **new here**: unreadable or non-UTF-8 files become error rows instead of
  crashing the OO scorer (PL-778).

## Develop

```bash
uv sync
make check   # ruff, mypy, pyright (tests), full pytest suite
```
