# Design Check Reference

The advisory `design` check, its rules, and the shadow
ratchet that compares findings against a base commit. For CI wiring, start
with [Configuring a Repo](CONFIGURING.md).

**Contents**

- [Advisory Design Check](#advisory-design-check)
- [Shadow Design Ratchet](#shadow-design-ratchet)
- [Design Evals](#design-evals)

## Advisory Design Check

`oo-ratchet design src/pkg/ [--json] [--layers FILE]` reports OO design smells the metric
gates cannot see: stateless classes with one public method (a function wearing
a class) or several (a namespace of free functions), getter-heavy classes, and
stateful concrete classes imported across top-level subpackages instead of a
Protocol/ABC. Findings exit 0 unless `--shadow-check REF --enforce` is given (below); invalid
input/configuration exits 2. It has no baseline file.

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

With the fixed four-ring table, two class and import rules are scoped by ring
(no table, or the declared-layers form, changes nothing):

- `stateless-single-method` and `stateless-function-bag` are not reported for
  classes in `adapters` or `entry` modules: a stateless codec or wiring class at
  the boundary is not a function-object strategy. They still fire in `domain`,
  `application` and unlayered modules.
- `concrete-cross-package-import` is not reported for imports made by an `entry`
  module: the entry ring is the composition root and wires concrete adapters. It
  still fires for imports made by every other ring and unlayered modules.

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

All design findings remain advisory and exit 0, unless `--shadow-check` runs with
`--enforce` (below). These ceilings are design signals, not new adopter ratchet
gates or changes to existing OO/coupling thresholds.

## Shadow Design Ratchet

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

**Shadow mode does not gate a build unless asked.** All findings and verdicts
exit **0**, even `would-fail`. Invalid paths, refs, layer configuration,
unreadable Python or parse errors exit **2** rather than presenting an incomplete
scan as an improvement. Existing adopter gates, thresholds and release behavior
are unchanged.

`--shadow-check REF --enforce` is the opt-in gate. It exits **1**, after printing
the report, when the comparison adds a finding of a **gate-capable** rule, and
writes the added keys to stderr. `--enforce` without `--shadow-check` exits 2.
Added findings of every other rule still exit 0.

Limits of the comparison: it matches findings by key (rule, module, symbol), so
moving a file that already has a finding reads as one removed and one added key
(exit 1), and swapping one forbidden import for another with the same exported
name reads as unchanged (exit 0). For an exact edge-by-edge check of forbidden
imports use the `layers` gate, which baselines module-pair edges.

Gate-capable rules are the ones measured right at least 90% of the time on vox,
quarry, lux and z-spec ([`architecture/b4-design-precision.md`](architecture/b4-design-precision.md) holds the
method, the raw labels and the table):

| Rule | Precision | Measured on |
|------|-----------|-------------|
| `layer-import` | 100% | all 608 findings |
| `unlayered-module` | 100% | all 168 findings |
| `thick-entry` | 100% | all 58 findings |
| `size-cap` | 100% | all 82 findings |
| `stateless-single-method` | 96% | 24 of 51 findings |

The first four state a fact about the code, rechecked by an independent count.
Their precision is relative to the declared layer table and the stated ceilings.

The other rules stay advisory, with the measured precision (true findings over
findings read): `misplaced-function` 2 of 2 (too few findings to rely on),
`stateless-function-bag` 67%, `concrete-cross-package-import` 67%, `data-clump`
57%, `middle-man` 50%, `tag-switch` 44%, `feature-envy` 41%, `envied-data` 38%,
`domain-io` 36%, `getter-heavy` 29%, `split-cohesion` 13%, `primitive-params`
10%.

## Design Evals

**Design evals.** `evals/design/` seeds eleven library-loan bad/good pairs with
shared behavior checks and stable `(rule, path, symbol)` keys in `expected.toml`.
`tests/test_design_evals.py` checks recall, precision and ordering for every seeded
rule. Known false positives remain strict xfails, never fixture workarounds
(none are open now: the ring-scoped rules above cleared the `decoys` codec and
`layer-leak` entry-wiring cases).
`make check` lints and type-checks the fixtures and runs the harness, but the
self-ratchets still scan only `src/oo_ratchet/`. The layer-leak and decoys pairs' `layers.toml`
is consumed by the scanner with `--layers` (and by the eval harness).
