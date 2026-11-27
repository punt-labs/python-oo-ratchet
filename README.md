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
adoption merge bootstrap-passes. The `layers` gate's one-time domain-purity
adoption merge also needs `--allow-config-change` on that run (see "Layers gate"). `oo-ratchet <gate> --help` lists each gate's
flags. Baseline and audit files (`.oo-baseline.json`, `.oo-audit.jsonl`,
`.oo-coupling-baseline.json`, ...) keep the same names as the embedded copies,
so a repo switches over without rebaselining.

### Namespace workspaces

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

### Layers gate

`oo-ratchet layers src/pkg/ [--check|--update|--json|--suggest]` turns the design check's layer rules into a shrinking baseline. It reads the same `[tool.oo-ratchet.layers]` table, either the fixed four-layer form or declared layers:

```toml
[tool.oo-ratchet.layers.kernel]
prefixes = ["paths", "log_*"]   # relative to the package; trailing * = string prefix
imports = []                     # layers kernel may import

[tool.oo-ratchet.layers.service]
prefixes = ["service", "hooks"]
imports = ["kernel"]
```

Each layer needs a non-empty `prefixes` list. A `*` may only end a prefix, and a prefix may not end in `.`. The longest prefix wins; an exact prefix beats a `*` prefix of equal length; the package root is exempt. A declared config affects only the layer rules: the design check's primitive-params, tag-switch and data-rule eligibility behave as with no config.

`src/pkg/` must be the package directory (it needs an `__init__.py` and at least one other module).

- `--check` fails on a violating import edge not in `.oo-layers-baseline.json` and on a baseline entry that no longer violates. It also fails when a non-root module matches no layer, or a layer matches no module, so a misspelled prefix cannot hide a package. The PASS line prints the modules scanned and unassigned counts.
- Against the merge base it fails if the baseline gained an edge, and if an edge violates under the base commit's `[tool.oo-ratchet.layers]` (read from the same `pyproject.toml` the scan used, as a repository-relative path; a base that has a baseline but no layer config there fails) and is not in the base baseline, so widening `imports` or narrowing `prefixes` in the same change as a new violation is caught.
- `--update` adopts a first baseline, then only shrinks it, refuses a package the layers do not fully cover, and appends `.oo-layers-audit.jsonl`.
- The repository (and so the baseline and audit files) is the git repository containing `src`, not the working directory; a `src` outside any repository is refused. The baseline is shared by the repository's packages, and each check or update reads and rewrites only the scanned package's rows. A baseline deleted after the base had one fails, even for a clean package.
- `--check` also fails when a layer's `imports` widens against the base config, or, with the fixed four-layer form on both sides, when a module present at both the base and the current tree is assigned to an outer layer than at the base (ring order entry, adapters, application, domain) or loses its layer (leaving `domain` is always outward). A module absent at the base is not a move: it is not compared, and its edges are not judged under the base config, only against the current config and the baseline. For a single positional package directory, the base's modules are the tracked `.py` files of the base commit (`git ls-tree`, so `export-ignore` and stray non-UTF-8 file names elsewhere do not matter, and a base holding only an `__init__.py`, or none, is fine), named by the same rule as the working tree. The base package is found at the same directory (a root package included), or, when that directory has no tracked Python at the base, by import name among the top-level packages (a directory under another regular package does not count): one match is the package moved to another directory, more than one fails the check with a message naming them instead of guessing, and none means the package is new and has nothing to compare. A `--namespace` or multi-root selection is not reconstructed from history: every current module counts as present, which is stricter, so a new module listed in an outer layer by name needs `--allow-config-change`. A direct `LayersRatchet` caller without a base-modules callback gets the same strict default. Moving a module toward `domain` is not widening, and declared layers compare `imports` only. With no layer config at the base, or no base ref, no move is checked. Land that as its own reviewed change with `--allow-config-change` (accepted with `--check` or `--update`; `--update` records `config_change` in the audit entry).
- `--update` writes the baseline atomically (temp file, then rename) and restores the previous one if the audit entry cannot be written. A package with no rows is adopted on `--update`; `--check` accepts that when the package does not exist at the base, and fails if an existing package gained rows. `--update` also drops rows of packages whose directory no longer exists in the repository, and records them as `retired` in the audit.
- `--base-ref`, `--require-base` and `--tripwire` are accepted only with `--check`; `--allow-ci-write` and `--source` behave as for coupling.

`oo-ratchet layers src/pkg/ --suggest` proposes a ring for each module and prints a starter fixed-form `[tool.oo-ratchet.layers]` table, then a comment line of reasons for each module. It needs no existing layers table, writes no file, and never touches `pyproject.toml` or the baseline: **the table is never applied automatically**, because a wrong ring silently passes forbidden imports. Review every reason, then copy the table in yourself. The output is valid TOML (all notes are comments) and always exits 0; it is sorted, so two runs print the same text. Names and reasons are printed with control characters and line breaks escaped, so a file name holding a newline cannot start an active TOML line when you paste the table. The rules run in this order and the first match wins:

1. `entry`: imports `argparse` or `typer` (not under `if TYPE_CHECKING:`), or is the module a `[project.scripts]` entry of the nearest `pyproject.toml` points at.
2. `adapters`: imports an IO module (the design check's `domain-io` list) or calls a bare `open`, and imports no `entry` module.
3. `application`: defines a top-level `typing.Protocol` class, imports no IO, and an `adapters` module imports it.
4. `domain`: imports no IO.

Exception to these rules: the package root (`pkg`) is placed in `entry` whatever it imports, because vox, lux and z-spec commit it there and only `entry` may import `entry`; a root that a non-entry module imports, or that has a relative import climbing above the package, is unclassified.

A module matching several rules takes the outermost; the reason line names the other rings it matched. The gate lets `domain` import only `domain`, and `application` import only `application` and `domain`, so after the rules any `domain` or `application` module that imports a module of a ring it may not, or an unclassified module, becomes unclassified itself, repeated until nothing changes. Imports are read with the gate's own edge extractor: re-exports through a package `__init__`, literal dynamic imports and `TYPE_CHECKING` imports count as they do for `--check`. Unclassified modules are printed as `unclassified` comments with the reason and left out of the table, so `--check` reports them as unassigned until you place them. That includes a module name shared by several files (`pkg/a.py` and `pkg/a/__init__.py`): the gate sees one module, so the name is one unclassified entry listing every file, and a module with a relative import that climbs above the package root. The package root (`pkg`) is placed in `entry`, as vox, lux and z-spec place it, because only `entry` may import `entry`; if a non-entry module imports it, it is listed as unclassified with the reason. A class is a Protocol only when its base resolves to `typing.Protocol` or `typing_extensions.Protocol` through the module's own imports (aliases and `import typing as t` count; `from other import Protocol` does not). Every `[project.scripts]` name that targets a module appears in its reason. A malformed `[project.scripts]` (not a table, or a value that is not a `module[:object] [extras]` entry point) is a one-line failure (exit 1); with no `pyproject.toml` the header says console scripts were not read. `--suggest` needs no git repository and starts no git process. Lists hold explicit module names (`[`, `*` and `?` in a name are escaped, since the gate matches entries as globs), except where a prefix is exact: `pkg.sub` and `pkg.sub.*` appear only when every module at or under `pkg.sub` has that ring (the glob also claims modules added later under it). `--suggest` cannot combine with `--check`, `--update` or `--json`.

With the fixed four-layer form, the gate also baselines domain purity: each IO module a `domain` module imports (the `domain-io` list in the design check, `TYPE_CHECKING`-only imports excepted) is an edge from that module to the IO module, for example `pkg.domain.model -> subprocess`, and a bare unbound `open(...)` call or a `builtins.open(...)` call (also through `import builtins as b`) or `from builtins import open` is an edge to `builtins.open`. A literal `importlib.import_module("subprocess")` or `__import__("socket")` is an edge to that IO module too; none of these count under `if TYPE_CHECKING:`, and a name inside the scanned package is never IO even when the package is called `rich` or `json`. A failure that lists a purity edge names the way out: a port in the application layer implemented in an adapter, or the one-time `--allow-config-change` update below. A new one fails `--check`; a removed one is a stale baseline entry that `--update` drops. Declared layers have no domain and no purity edges.

An adopter whose domain modules already import IO adopts these edges once: run `oo-ratchet layers src/pkg/ --update --allow-config-change --source <ref>` and commit the baseline. CI runs `--check --allow-config-change` with the merge-base `--base-ref` in that PR, and the post-merge `push: [main]` run of that one merge commit also passes `--allow-config-change` (`--check --base-ref HEAD~1 --require-base --tripwire --allow-config-change`), because `HEAD~1` lacks the edges; drop the flag from both once it has merged. With the flag, `--update` may add edges whose layer class is `io` (the audit entry lists them under `added` next to `config_change`), and `--check` does not count them as baseline growth over the base or as violations under the base config. Any other new edge is still refused with the flag. Without the flag nothing changes: such an update is refused and such a check fails.

The gate over-approximates: it must never pass a forbidden import, and a rare false positive is fixed by restructuring. Edges counted: imports anywhere in a module (functions included) and `TYPE_CHECKING` imports (as in the design check).

- **Re-exports.** `from pkg import X` is an edge to every module the package's `__init__` imports `X` from, on any path: an import anywhere in the `__init__` counts (module scope, any block, function bodies, `import a.b as X`), and rebinding, `del`, annotations, `with ... as X` or `__all__` never remove it. A wildcard `from M import *` in an `__init__` makes every name imported from that package an edge to `M` as well, transitively through chained wildcards.
- **Dynamic imports.** Any call anywhere in a module (body, function bodies, defaults, decorators, class bodies, lambdas) whose callee's final name or attribute is `import_module` or `__import__`, with a literal string name (positional or `name=`; a relative name resolved with a literal `package`), is an edge when the name is a module of the scanned package. There is no binding analysis: a method of an unrelated object called `import_module` is a deliberate false positive, and so is a call after the name was rebound. Names aliased with `from importlib import import_module as x` or `x = importlib.import_module` count in any scope.
- A relative import that climbs above the package root fails the check ("unresolvable relative import", with file and line). Computed module names and attribute access on an imported package (`import pkg; pkg.a.f()`) are out of scope.
- Git failures (`ls-files`, `ls-tree`) fail the gate closed. Retired-row detection reads the working tree, so an unstaged deletion retires. The audit log is appended with one write per record and cut back on failure; the baseline is replaced atomically and keeps its file mode (0644 for a new file).

Wiring `layers` into this repository's own `Makefile` and CI needs a layer design for `oo_ratchet` itself and is a follow-up.

### Advisory design check

`oo-ratchet design src/pkg/ [--json] [--layers FILE]` reports OO design smells the metric
gates cannot see: stateless classes with one public method (a function wearing
a class) or several (a namespace of free functions), getter-heavy classes, and
stateful concrete classes imported across top-level subpackages instead of a
Protocol/ABC. Findings always exit 0; invalid input/configuration exits 2.
It has no baseline and is not part of adopter `make check` gates.

Optional layers come from the **nearest** `pyproject.toml` above the scanned
package, or `--layers FILE` (the same TOML table):

```toml
[tool.oo-ratchet.layers]
entry = ["pkg", "pkg.cli*"]
adapters = ["pkg.adapters", "pkg.adapters.*"]
application = ["pkg.application", "pkg.application.*"]
domain = ["pkg.domain", "pkg.domain.*"]
```

Globs match full dotted module names, case-sensitively; `*` spans dots.
Overlaps use the first match in **entry → adapters → application → domain**
order, regardless of TOML order. Root `__init__.py` is named `pkg`. Missing
layer keys mean empty lists; unknown keys or non-list/non-string values error.
No table means no layer findings; an empty table marks every module unlayered.

- `layer-import`: imports an in-tree module in a layer further out, including
  relative, submodule and `TYPE_CHECKING` imports.
- `domain-io`: imports subprocess, socket, shutil, json, sqlite3, httpx, requests,
  urllib.request, typer, rich, mcp, fastmcp, logging.handlers, os, os.path,
  pathlib, io, tempfile or glob. Findings are purely import-based, once per
  imported module per import statement, keyed by that module; `TYPE_CHECKING`
  imports are exempt. Even `os.path.join` or `PurePath` usage triggers the rule.
  Domain code reaches the filesystem and environment through an injected port.
  Bare `open(...)` calls also fire, but any binding of `open` anywhere in the
  module (including parameters, nested definitions and pattern captures)
  suppresses all of them. Qualified calls and dynamic imports are not analyzed;
  there is no alias, scope or control-flow inference.
- `unlayered-module`: matches no declared glob.
- `thick-entry`: an entry function/method exceeds cyclomatic complexity 4,
  using the same scope-aware computation as the OO metrics.

Data-placement checks run **without** layer configuration too. With a table,
declarations and consumers in `entry` or `adapters` are excluded; application,
domain and unlayered modules remain eligible:

- `envied-data` (D1): a dataclass, NamedTuple, attrs-like or slotted data class
  with no public behavior beyond properties has at least two distinct fields
  read together in a function in another module. Keyed on the data class.
- `feature-envy` (D2): a function reads at least three distinct attributes of
  one explicitly typed project-class parameter; in methods that must exceed
  the number read on `self`. `from_*` classmethods are exempt.
- `data-clump` (D3): at least four field/parameter names are shared by at least
  three class/signature owners. Names occurring in fewer than three owners are
  pruned before pairwise intersections, retaining maximal sets for each identical
  owner group. Higher-order subsets can still be missed when every pair has extra
  names that survive this global frequency filter. Each occurrence
  is keyed on its owner, with comma-separated sorted names in `detail`.
  Overload stubs and Protocol methods are not owners. A class and its methods
  count as one independent owner, reported once on the first matching declaration
  (the class when its fields match). Separate signature name sets are never
  unioned to fabricate support.
- `misplaced-function` (D4): a public module function's first positional
  parameter is annotated with a project class, or its return annotation names
  a project class whose fields it reads. `create_*` functions are exempt.

These are syntactic checks, not type or flow analysis. Receivers are typed only
by parameter annotations, local annotations, or a direct `name = ProjectClass(...)`
assignment to an imported or locally declared project class name. Repeated
bindings (including a parameter's initial binding) discard a receiver's type;
statement order is irrelevant. Import aliases and re-exports are followed as
module-level declarations only; any repeated module-level binding makes the
name ambiguous, regardless of statement order or branch. Other bindings include captures, loop/with
targets, imports, nested def/class names, walrus targets, global/nonlocal
declarations and deletions. Value aliases, factory results, call chains and container
annotations do not propagate receiver types. Nested function bodies are checked
separately, not attributed to their enclosing function.
Direct constructor assignment is ignored when the constructor name is bound
anywhere in that function; explicit annotations remain separate syntactic sources.

Additional advisory shape checks run with the same syntactic project-class index:

- `primitive-params` (D5): public signatures with at least two `str`, `int`,
  `float`, `bool`, `dict` or unannotated parameters, excluding the receiver.
  With layers configured, only domain modules qualify; without layers it applies
  everywhere. Nested functions and private APIs are not public signatures.
- `tag-switch` (D6): an if/elif chain or match with at least three literal or
  enum-member-form arms on the same name/attribute. Adapter modules are exempt.
  Contiguous same-block `if` arms ending directly in `return` or `raise` also
  form a chain; intervening statements and nested bodies break that sequence.
  Qualified member spellings are syntactic; external enum values are not inferred.
- `middle-man` (D7): at least two public methods, all single-call forwarding to
  the same `self.<field>` collaborator. Explicit Protocol subclasses are exempt.
- `split-cohesion` (D8): LCOM4 exceeds one for at least three instance methods,
  connected through shared `self` fields or direct calls to each other.
  Static/class methods, property/cached-property accessors (including setters
  and deleters), and `__init__`, `__new__`, `__post_init__` do not enter
  the count or graph. Nested declaration bodies do not contribute edges.
- `size-cap`: modules over 400 code lines, classes over 25 methods, signatures
  over five parameters, or complexity over ten. Code lines and complexity use
  existing ratchet measures; parameter counting excludes receivers and variadics.
  A symbol has one finding with all exceeded measures in `detail`; module overflow
  is keyed on `<module>`. These caps apply regardless of layer.

All design findings remain advisory and exit 0. These ceilings are design signals,
not new adopter ratchet gates or changes to existing OO/coupling thresholds.

### Shadow design ratchet

```bash
oo-ratchet design src/pkg/ --shadow-check origin/main
oo-ratchet design src/pkg/ --shadow-check origin/main --layers layers.toml --json
```

Shadow mode scans the source at the Git merge-base of the reference and `HEAD`,
then scans the working tree, including uncommitted Python files. It uses the OO
gate's Git adapter and per-file metric comparison; no baseline file or audit
waiver is read. The base scan uses an isolated detached worktree that is removed
afterward. Without `--layers`, each tree discovers its own layer configuration;
an explicit override is applied to both scans.

Design debt is a multiset of `(rule, module, symbol)` keys: line numbers and
diagnostic detail do not participate. Each finding contributes one occurrence;
an increased count adds debt even when that key already exists. Reports repeat
a key once per added or removed occurrence, in sorted order.
Modules are dotted names rooted at the scanned
package (`pkg.sub`, including its `__init__.py`), not checkout paths. Renames are
reported as added and removed keys, never matched or netted against each other.
If a module and a package share an import name (`foo.py` and `foo/__init__.py`),
both are scanned. The package retains `pkg.foo`; the shadowed file uses a
source-relative identity such as `pkg:foo.py`. Layer matching and relative
imports still use the logical import spelling for both files.

The ordered, unweighted verdict is:

1. Any added Tier 0 key (`size-cap`, `layer-import`, `domain-io`):
   **`would-fail: tier0`**.
2. Any added Tier 1 key (every other design rule): **`would-fail: tier1`**.
3. Otherwise, any removed Tier 1 key: **`good-deed: trade`**. This is a
   repository-wide trade; any Tier 2 regressions are explicitly accepted.
4. Otherwise, any Tier 2 per-file OO metric regression: **`would-fail: tier2`**.
5. A Tier 2 improvement and no regression: **`good-deed`**; else **`neutral`**.

Removing only Tier 0 debt does not buy a trade. Tier 2 reuses the existing OO
comparison and new-file absolute checks, with no rename matching or weighted
sum. Text prints the verdict, added/removed keys for each design tier, then
per-file OO metric deltas; JSON includes the same content, improved/regressed
lists and accepted regressions. Both formats have deterministic ordering and
are byte-identical on repeat runs against unchanged inputs.

**Shadow mode never gates a build.** All findings and verdicts exit **0**, even
`would-fail`. Invalid paths, refs, layer configuration, unreadable Python or parse
errors exit **2** rather than presenting an incomplete scan as an improvement.
Existing adopter gates, thresholds and release behavior are unchanged.

**Design evals.** `evals/design/` seeds eleven library-loan bad/good pairs with
shared behavior checks and stable `(rule, path, symbol)` keys in `expected.toml`.
`tests/test_design_evals.py` checks recall, precision and ordering for every seeded
rule. Known false positives remain strict xfails, never fixture workarounds.
`make check` lints and type-checks the fixtures and runs the harness, but the
self-ratchets still scan only `src/oo_ratchet/`. The layer-leak pair's `layers.toml`
is consumed by the scanner with `--layers` (and by the eval harness).

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

## Diagnostics and usage telemetry

Gate reports and `--json` output go to stdout only. Each `oo-ratchet` run also
writes diagnostics (gate start and finish, baseline and audit writes, git
degradation) through the shared
[`punt-observe`](https://pypi.org/project/punt-observe/) package to a private,
redacted, rotated log at `~/.punt-labs/oo-ratchet/logs/oo-ratchet.log`;
warnings and errors are echoed to stderr.

Each run also records one local usage event, `oo-ratchet.cli.<gate>` version
1, carrying only its outcome (`pass`, `fail`, `invalid`, `error`) and duration,
in `~/.punt-labs/oo-ratchet/telemetry.db` (90-day retention). No paths, source,
baselines or report text are recorded and nothing leaves the machine.
`PUNT_TELEMETRY=off` or `OO_RATCHET_TELEMETRY=off` turns capture off without
affecting the log.

## Reference (0.4.x)

### Targets and counting rules

The OO targets are fixed in
[`oo/thresholds.py`](src/oo_ratchet/oo/thresholds.py), not configurable.
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
findings measure design better than module size or shape does; they remain
advisory until their precision on adopter repositories is measured (PL-1685).

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

Since 0.3.0, [`CodeLines`](src/oo_ratchet/oo/code_lines.py) excludes blank lines,
comment-only lines, and module/class/function/async-function docstrings.
Trailing comments do not remove the code line. Non-docstring strings count,
including nonblank lines spanned by multiline strings; a docstring sharing a
line with real code does not remove that code. A physical line counts once.

[`ClassKinds`](src/oo_ratchet/oo/class_kinds.py) excludes these from the
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
[`tests/test_update_backfill.py`](tests/test_update_backfill.py).

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

- **quarry**: coupling `--tripwire`, `tokenize`-based suppression scan, and an
  extraction waiver for the two class-shape ratios, since removed with those
  ratios.
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
