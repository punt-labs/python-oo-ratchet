# Configuring a Repo

How to set up a Python repository to use `oo-ratchet`. The steps run in
order: install the tool, adopt the three baseline gates, set options in
`pyproject.toml`, add layer rules, and wire everything into `make` and CI.

Every command here was run on a small scratch package, `shop`. Paths, hashes
and the merge-base SHA differ in your repo.

**Contents**

- [Install](#install)
- [Choose Gates and Their Order](#choose-gates-and-their-order)
- [Adopt the Baseline Gates](#adopt-the-baseline-gates)
- [Settings in pyproject.toml](#settings-in-pyprojecttoml)
- [Adopting Clean Architecture with oo-ratchet](#adopting-clean-architecture-with-oo-ratchet)
- [Makefile Targets](#makefile-targets)
- [CI Workflow](#ci-workflow)
- [Where State Files Live](#where-state-files-live)
- [Changing a Baseline Later](#changing-a-baseline-later)

## Install

`oo-ratchet` needs Python 3.13 or newer. Add it as a development dependency:

```bash
uv add --dev punt-oo-ratchet
```

Or install it with pip:

```bash
pip install punt-oo-ratchet
```

Or run it once without installing:

```bash
uvx --from punt-oo-ratchet oo-ratchet --help
```

The examples below use `uv run oo-ratchet`. Drop `uv run` if the command is on
your `PATH`.

## Choose Gates and Their Order

A gate is one check that compares your code against a recorded state. Turn
them on one at a time, in this order. Each step is its own pull request.

| Step | Gate | Why this order |
|------|------|----------------|
| 1 | `suppressions` | No setup. It counts `noqa` and `type: ignore` comments and needs no config. |
| 2 | `oo` | No setup. It records today's scores and stops them from getting worse. |
| 3 | `coupling` | No setup. Same idea for imports and class cohesion. |
| 4 | `layers` | Needs a ring table you write. See the Clean Architecture guide below. |
| 5 | `design` | Best after `layers`, because the layer rules need the table. |

A ring is a named layer of the package, such as `domain`. The `layers` gate
fails when a module imports from a ring it may not use.

## Adopt the Baseline Gates

A baseline is the saved scores for each file, kept in a JSON file at the
repository root. The first `--update` writes it. Run these from the
repository root, once per gate, with your package directory in place of
`src/shop/`:

```bash
uv run oo-ratchet suppressions src/shop/ --update
```

```bash
uv run oo-ratchet oo src/shop/ --update
```

```bash
uv run oo-ratchet coupling src/shop/ --update
```

The `oo` and `coupling` updates print each file they recorded as
`backfilled`. The `suppressions` update prints the counts by category. Commit
the new `.oo-baseline.json`, `.oo-coupling-baseline.json`,
`.suppression-baseline.json` and the `.jsonl` audit logs next to them.

From then on, `--check` compares your branch with the main branch. In a pull
request, pass the merge-base SHA, the commit where your branch left main. An
explicit `origin/main` would also pull in later main changes.

```bash
uv run oo-ratchet oo src/shop/ --check --base-ref "$(git merge-base origin/main HEAD)" --require-base
```

Here is a real failure, from a branch that added a class with an explicit
`__init__` and one `noqa` comment. Rows for metrics that passed and one
`FAIL: baseline out of date` line are left out:

```text
File                                     Metric                       Baseline    Current    Delta     Status
------------------------------------------------------------------------------------------------------------
src/shop/application/checkout.py         encapsulation_ratio             1.000      0.000   -1.000  REGRESSED
src/shop/application/checkout.py         init_violations                 0.000      1.000   +1.000  REGRESSED
src/shop/application/checkout.py         public_attr_violations          0.000      1.000   +1.000  REGRESSED
FAIL: regression detected
FAIL: no metric improved on any touched file
```

Fix the code, run `--update` again for the changed files, and commit the
rewritten baseline with your change. `--update` never loosens a recorded
score. [Changing a Baseline Later](#changing-a-baseline-later) covers the
audited ways to accept a worse score.

On the first run, before any baseline exists on `main`, `--check` prints
`No baseline at base or origin/main tip -- first-adoption bootstrap pass` and
passes.

## Settings in pyproject.toml

All settings live in `pyproject.toml` under `[tool.oo-ratchet]`. With none,
the strict defaults apply. An unknown key inside a table is an error, not
ignored: a typo such as `bogus = 1` under the coupling table prints
`FAIL: unknown [tool.oo-ratchet.coupling] keys: ['bogus']` and exits 1.

### Coupling Settings

```toml
[tool.oo-ratchet.coupling]
stateless-values = "any"

[tool.oo-ratchet.coupling.caps]
"src/pkg/facade.py" = { efferent_coupling = 20 }
```

- `stateless-values` decides which classes the cohesion score (LCOM, the
  share of method pairs that touch no common field) skips. `"dataclass"` is
  the default: it skips only `@dataclass` or `__slots__ = ()` classes that
  store no instance state. `"any"` skips every class that never writes a
  private `self._*` attribute.
- `caps` replaces one metric's default target for one exact
  repository-relative file path. The example lets a wiring file import 20
  modules instead of 10. A cap applies to that file only.

### Layers Settings

The `layers` and `design` gates read the ring table. The fixed four-ring form
names the rings `entry`, `adapters`, `application` and `domain`. Each ring is
a list of dotted module names, and a trailing `*` matches everything below it:

```toml
[tool.oo-ratchet.layers]
entry = ["shop", "shop.cli"]
adapters = ["shop.adapters", "shop.adapters.*"]
application = ["shop.application", "shop.application.*"]
domain = ["shop.domain", "shop.domain.*", "shop.rules", "shop.helpers"]
```

A module may import only its own ring or one nearer the domain. `domain` may
import only `domain`, and no IO module. The table can also declare your own
layer names. See [What the Gate Checks](LAYERS.md#what-the-gate-checks).

### Suggest Settings

`layers --suggest` guesses a ring from a package name. Rename the names it
looks for with a table of lists. Any other key, or a value that is not a
list, exits 1:

```toml
[tool.oo-ratchet.suggest]
domain = ["logic"]
```

### Telemetry Settings

Each run records one local usage event with an outcome and a duration (see
[Diagnostics and Usage Telemetry](REFERENCE.md#diagnostics-and-usage-telemetry)).
Two keys under `[tool.oo-ratchet]` control it:

```toml
[tool.oo-ratchet]
telemetry = false
telemetry-retention-days = 30
```

- `telemetry = false` turns capture off for this project. The default is
  `true`. `PUNT_TELEMETRY=off` and `OO_RATCHET_TELEMETRY=off` in the
  environment also turn it off, and any one of the three wins.
- `telemetry-retention-days` is how long events are kept, 1 to 3650. The
  default is 90.

### Source Selection

A package split across several directories is one scan. Name the shared
top-level package and its roots:

```toml
[tool.oo-ratchet]
namespace = "punt_lux"
roots = ["packages/*/src/punt_lux"]
```

The details are in
[Namespace Workspaces](REFERENCE.md#namespace-workspaces).

## Adopting Clean Architecture with oo-ratchet

This guide takes a package from "no layer rules" to two CI gates: the
`layers` gate (a baseline of forbidden import edges that only shrinks) and
the `design` gate (no new finding of a rule that is reliably right).
The scratch package `shop` has `domain`, `application` and `adapters`
subpackages, a `cli.py` and two loose modules.

The four rings are `entry` (wires things together, the outermost),
`adapters` (IO), `application` (use cases) and `domain` (pure rules). A
module may import only its own ring or one nearer the domain. `domain` may
import only `domain`, and no IO module.

### 1. Ask for a Starting Table

```bash
uv run oo-ratchet layers src/shop/ --suggest
```

The command writes nothing and exits 0. It exits 1 when a
`[tool.oo-ratchet.suggest]` table is invalid. It prints a starter
`[tool.oo-ratchet.layers]` table, then three comment lists and a summary
line, each entry with its reason:

- `# Ring from declaration, name or entry evidence:` modules whose ring
  someone declared or named. A declaration is a module-level
  `__ring__ = "domain"`, one of `entry`, `adapters`, `application` or
  `domain`. It is read from the syntax tree and the module is never imported.
  Otherwise a package name decides: `domain`, `model`, `models`, `core` mean
  domain; `application`, `usecases`, `use_cases` mean application; `adapters`,
  `adapter`, `infra`, `infrastructure` mean adapters. Your own names go in a
  `[tool.oo-ratchet.suggest]` table. The one ring taken from evidence is
  `entry`: a module importing `argparse` or `typer`, or a `[project.scripts]`
  target.
- `# Conflicts:` a module whose declared or named ring evidence refutes. A
  `domain` module that reaches IO, directly or through the modules it
  imports, is a conflict, and the reason prints the chain.
- `# Unclassified:` no declaration and no package name. The reason shows what
  IO the module reaches.
- `# Summary:` the counts.

On `shop` the table and lists were:

```text
[tool.oo-ratchet.layers]
entry = [
    "shop",
    "shop.cli",
]
adapters = [
    "shop.adapters",
    "shop.adapters.*",
]
application = [
    "shop.application",
    "shop.application.*",
]
domain = [
    "shop.domain",
    "shop.domain.pricing",
    "shop.rules",
]

# Ring from declaration, name or entry evidence:
#   shop: entry (package root (placed in entry by vox, lux and z-spec))
#   shop.adapters: adapters (name convention: package `adapters`; reaches no IO)
#   shop.adapters.store: adapters (name convention: package `adapters`; reaches IO: shop.adapters.store -> json)
#   shop.application: application (name convention: package `application`; reaches no IO)
#   shop.application.checkout: application (name convention: package `application`; reaches no IO)
#   shop.cli: entry (imports argparse, console script shop)
#   shop.domain: domain (name convention: package `domain`; reaches no IO)
#   shop.domain.pricing: domain (name convention: package `domain`; reaches no IO)
#   shop.rules: domain (__ring__ marker; reaches no IO)

# Conflicts:
#   shop.domain.export: CONFLICT (name convention: package `domain` says domain, but reaches IO: shop.domain.export -> json)
#   shop.domain.ledger: CONFLICT (name convention: package `domain` says domain, but reaches IO: shop.domain.ledger -> shop.adapters.store -> json)

# Unclassified:
#   shop.helpers: unclassified (no declaration or package name convention; reaches no IO)

# Summary: 7 of 12 modules ring-assigned from a declaration or name, 2 from entry evidence, 2 conflicts, 1 unclassified.
```

(The header comments are left out here.) Nothing is applied for you: a wrong
ring silently passes forbidden imports, so a person reads every reason first.
The full rules are in
[Starter Table From suggest](LAYERS.md#starter-table-from-suggest).

### 2. Write or Correct the Table

Copy the table into `pyproject.toml`, then fix it by hand. The two conflicts
are real: `shop.domain.export` imports `json` and `shop.domain.ledger`
imports an adapter. A conflict stays out of the suggested table, so decide for
each: move the code (the right fix), or keep it in `domain` for now and
baseline it in step 3. The unclassified `shop.helpers` is pure, so it joins
`domain`. You can also write `__ring__ = "domain"` in the module. The table
`shop` ended up with:

```toml
[tool.oo-ratchet.layers]
entry = ["shop", "shop.cli"]
adapters = ["shop.adapters", "shop.adapters.*"]
application = ["shop.application", "shop.application.*"]
domain = ["shop.domain", "shop.domain.*", "shop.rules", "shop.helpers"]
```

If you copy the suggested table as it is, `--check` refuses it, because the
conflicts and unclassified modules are unassigned:

```text
FAIL: the layer contract does not cover the package:
  unassigned module: shop.domain.export
  unassigned module: shop.domain.ledger
  unassigned module: shop.helpers
```

### 3. Baseline Today's Violations

With the table complete, `--check` lists what violates it:

```bash
uv run oo-ratchet layers src/shop/ --check
```

```text
FAIL: layer violations not in the baseline:
  shop.domain.export -> json  (domain -> io)
  shop.domain.ledger -> shop.adapters.store  (domain -> adapters)
  domain purity: move the IO behind a port in the application layer, implemented in an adapter; or accept the edge once with `oo-ratchet layers --update --allow-config-change --source <ref>`
```

Adopt them as the first baseline. A first `--update` needs no extra flag. It
writes `.oo-layers-baseline.json` and appends `.oo-layers-audit.jsonl`:

```bash
uv run oo-ratchet layers src/shop/ --update
```

```text
Wrote /path/to/repo/.oo-layers-baseline.json
  violations: 2 (0 removed)
```

Commit the table, both files and the code in one change. On a branch,
`--check` compares against a base commit, so the base must exist locally
(`git fetch origin main`). Pass the merge base, as this repository's CI does:

```bash
uv run oo-ratchet layers src/shop/ --check --base-ref "$(git merge-base origin/main HEAD)" --require-base
```

```text
PASS: 12 modules scanned, 0 unassigned, 2 baselined layer violations, none new/stale
```

### 4. Shrink It

Fix a violation. Here `shop.domain.ledger` takes its prices as an argument
instead of importing the store. `--check` now says the baseline is stale, and
`--update` drops the entry. It never adds a violation:

```bash
uv run oo-ratchet layers src/shop/ --check --base-ref "$(git merge-base origin/main HEAD)" --require-base
```

```text
FAIL: baseline entries that no longer violate (--update):
  shop.domain.ledger -> shop.adapters.store
```

```bash
uv run oo-ratchet layers src/shop/ --update
```

```text
Wrote /path/to/repo/.oo-layers-baseline.json
  violations: 1 (1 removed)
```

`--base-ref`, `--require-base` and `--tripwire` belong to `--check` only. With
`--update` they are a usage error (exit 2):

```text
oo-ratchet layers: error: --base-ref, --require-base and --tripwire need --check
```

A new violation is refused by `--update`. For a purity edge, such as
`shop.domain.pricing -> os`, the refusal names the way out:

```text
FAIL: refusing to baseline new layer violations:
  shop.domain.pricing -> os
  domain purity: move the IO behind a port in the application layer, implemented in an adapter; or accept the edge once with `oo-ratchet layers --update --allow-config-change --source <ref>`
```

Accepting it once, as its own reviewed change, takes `--allow-config-change`.
That flag only ever admits edges to IO, never a layer edge:

```bash
uv run oo-ratchet layers src/shop/ --update --allow-config-change
```

```text
Wrote /path/to/repo/.oo-layers-baseline.json
  violations: 2 (0 removed)
```

The audit row records `"config_change":true`. This applies to a change made
after the adoption change has merged, so the base contains the baseline.
Then `--check` against a base that lacks the edge fails until you pass
`--allow-config-change` to it as well, in that one change:

```bash
uv run oo-ratchet layers src/shop/ --check --base-ref "$(git merge-base origin/main HEAD)" --require-base --allow-config-change
```

```text
PASS: 12 modules scanned, 0 unassigned, 2 baselined layer violations, none new/stale
```

Without the flag, the same check prints `FAIL: baseline holds edges the base
<sha> did not` and `FAIL: edges that violate under the base config, not in
the base baseline`. After that change merges, drop the flag from CI. While
the base has no baseline at all, as in the adoption pull request itself, the
whole baseline is the first one and a purity edge passes without the flag. If
`main` gained the baseline after you branched, merge `main` first so the
comparison runs.

To draw the rings, `layers --json` prints `module_rings`, `ring_edges` and
`marked_violations` along with the older keys:

```bash
uv run oo-ratchet layers src/shop/ --json
```

### 5. Add the Design Gate

`design` finds smells the import baseline cannot. With `--shadow-check REF`
it compares the findings of your tree against the merge base of `REF` and
`HEAD`, and prints a verdict. A shadow check is that comparison against a
base commit. Alone it always exits 0. With `--enforce` it exits 1 when the
change adds a finding of a gate-capable rule, and prints the added keys:

```bash
uv run oo-ratchet design src/shop/ --shadow-check origin/main --enforce
```

For a branch that adds `shop/domain/audit.py`, importing the application
layer from `domain`, the command exited 1 and printed:

```text
oo-ratchet design: --enforce: 1 added gate-capable finding(s): (layer-import, shop.domain.audit, checkout)
would-fail: tier0 (shadow; advisory)
merge-base: 95c6232af577de122ac20a8a9cef6abf2f92d7ef
tier0 added (1):
  (layer-import, shop.domain.audit, checkout)
tier0 removed (0):
tier1 added (0):
tier1 removed (0):
tier2 deltas:
```

The per-file OO metric rows that follow are left out. On a branch with no
added finding it exits 0 and prints `neutral`. A change that adds an advisory
finding, or regresses an OO metric, prints `would-fail: tier1` or `tier2` and
still exits 0, because `--enforce` blocks only added findings of
gate-capable rules. Without `--shadow-check`, `--enforce` exits 2
(`--enforce needs --shadow-check`). A `REF` with no merge base with `HEAD`
exits 2 too.

The adoption change is the one exception. `design` reports layer findings only
where a layer table exists, and the base commit has none, so every forbidden
import the table leaves in the first baseline counts as added. On the `shop`
adoption branch (table plus two baselined violations),
`design src/shop/ --shadow-check <pre-adoption sha> --enforce` exited 1 and
listed `(domain-io, shop.domain.export, json)` and
`(layer-import, shop.domain.ledger, store)` as added. So in the adoption change
and its `main` run, run the design step without `--enforce`. It exits 0 and
only reports. Add `--enforce` in the next change. From then on the base has
the table: a branch that touched only `helpers.py` exited 0 and printed
`neutral`.

Only the rules measured right at least 90% of the time on vox, quarry, lux and
z-spec gate. The method and the raw labels are in
[`docs/architecture/b4-design-precision.md`](architecture/b4-design-precision.md).

| Gate-capable rule | Precision | Findings read |
|-------------------|-----------|---------------|
| `layer-import` | 100% | 608 of 608 |
| `unlayered-module` | 100% | 168 of 168 |
| `thick-entry` | 100% | 58 of 58 |
| `size-cap` | 100% | 82 of 82 |
| `stateless-single-method` | 96% | 24 of 51 |

The first four state a fact about the code, so their precision is relative to
your layer table and the stated ceilings. Every other rule stays advisory
(`stateless-function-bag` and `concrete-cross-package-import` 67%,
`data-clump` 57%, `middle-man` 50%, down to `primitive-params` 10%). The
design gate matches findings by rule, module and symbol, so it is looser than
the `layers` gate on imports. The two gates are meant to run together.

### 6. Wire Both Into CI

Add two targets to the `Makefile`, as this repository does. The design target
has a `DESIGN_ENFORCE` variable for the adoption change; this repository has
already adopted, so its own target always enforces:

```make
check-layers:
	uv run oo-ratchet layers src/shop/ --check $(LAYERS_BASE)
check-design:
	uv run oo-ratchet design src/shop/ $(DESIGN_BASE) $(DESIGN_ENFORCE)
```

Define `DESIGN_ENFORCE ?= --enforce` next to `DESIGN_BASE`. The adoption
change and its `main` run pass `DESIGN_ENFORCE=` (empty), for the reason given
in step 5. The full Makefile and the workflow are in the next two sections.

On `shop`, `make check-layers LAYERS_BASE="--base-ref origin/main --require-base"`
printed the `PASS` line shown above, and
`make check-design DESIGN_BASE="--shadow-check origin/main"` printed the
verdict and per-file rows.

The `main` form of the layers check, run directly on `shop`:

```bash
uv run oo-ratchet layers src/shop/ --check --base-ref HEAD~1 --require-base --tripwire
```

```text
PASS: 12 modules scanned, 0 unassigned, 1 baselined layer violations, none new/stale
```

`--tripwire` marks the run after a merge to `main`. A missing baseline at the
base then counts as the one-time adoption merge and passes. If the merge also
adds purity edges (step 4), the pull request check and the `main` run both
take `--allow-config-change`, and the next change removes it.

### 7. What to Commit, and What Fails Closed

Commit `.oo-layers-baseline.json` and `.oo-layers-audit.jsonl` with the code
that changes them, and the `[tool.oo-ratchet.layers]` table with
`pyproject.toml`. The design gate has no state file. `--suggest` writes
nothing. Both files live at the root of the git repository that holds the
package, one baseline shared by every package in it.

The gates fail closed. A failure is never a silent pass:

- `layers --check --base-ref REF --require-base` with an unresolvable `REF`
  prints `FAIL: base ref unresolvable and --require-base is set` and exits 1.
- `--check` on a branch whose merge base cannot be found, with a baseline in
  the tree, prints `FAIL: cannot resolve merge-base (origin/main unfetched or
  stale) with an in-tree baseline present; fetch origin/main or pass
  --base-ref` and exits 1.
- A module no layer claims, or a layer that claims no module, fails `--check`
  as unassigned, so a misspelled pattern cannot hide a package.
- A baseline entry for an edge that no longer exists fails `--check` until
  `--update` drops it, and a baseline that gained an edge over the base fails.
- `design --shadow-check` with a bad ref, a bad layer table or a file that
  does not parse exits 2 rather than reporting an incomplete scan as an
  improvement.
- `--update` and the other writes refuse under `GITHUB_ACTIONS=true` without
  `--allow-ci-write`.

## Makefile Targets

One target pair per gate keeps the commands in one place. The `*_BASE`
variables are empty by default and CI fills them in:

```make
SRC := src/pkg/
OO_BASE ?=
COUPLING_BASE ?=
SUPPRESSION_BASE ?=
LAYERS_BASE ?=
DESIGN_BASE ?= --shadow-check origin/main
DESIGN_ENFORCE ?= --enforce

check-oo:
	uv run oo-ratchet oo $(SRC) --check $(OO_BASE)
update-oo:
	uv run oo-ratchet oo $(SRC) --update $(OO_BASE)
check-coupling:
	uv run oo-ratchet coupling $(SRC) --check $(COUPLING_BASE)
check-suppressions:
	uv run oo-ratchet suppressions $(SRC) --check $(SUPPRESSION_BASE)
check-layers:
	uv run oo-ratchet layers $(SRC) --check $(LAYERS_BASE)
check-design:
	uv run oo-ratchet design $(SRC) $(DESIGN_BASE) $(DESIGN_ENFORCE)
```

Locally, `make check-oo` compares your working tree with the merge base of
`origin/main` and `HEAD`. To check a branch exactly as CI does, pass the
merge-base SHA:

```bash
make check-oo OO_BASE="--base-ref $(git merge-base origin/main HEAD) --require-base"
```

`oo-ratchet <gate> --help` lists each gate's flags.

## CI Workflow

The checkout needs full history, because the gates read the baseline at the
merge base. On a pull request, pass the merge-base SHA. After the merge, on
`main`, compare with the previous commit and add `--tripwire`. This step list
is modelled on this repository's own workflow (`.github/workflows/ci.yml`),
which also runs `make lint type test` and lets `release/*` branches pass the OO
gate without an improvement by adding `--allow-no-improvement`:

```yaml
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Ratchets (PR)
        if: github.event_name == 'pull_request'
        env:
          BASE_REF: ${{ github.base_ref }}
        run: |
          git fetch --no-tags origin "${BASE_REF}"
          BASE="$(git merge-base "origin/${BASE_REF}" HEAD)"
          make check-oo OO_BASE="--base-ref ${BASE} --require-base"
          make check-coupling COUPLING_BASE="--base-ref ${BASE} --require-base"
          make check-suppressions SUPPRESSION_BASE="--base-ref ${BASE} --require-base"
          make check-layers LAYERS_BASE="--base-ref ${BASE} --require-base"
          make check-design DESIGN_BASE="--shadow-check ${BASE}" DESIGN_ENFORCE=
      - name: Ratchets (main)
        if: github.event_name == 'push'
        run: |
          make check-oo OO_BASE="--base-ref HEAD~1 --require-base --allow-no-improvement --tripwire"
          make check-coupling COUPLING_BASE="--base-ref HEAD~1 --require-base --tripwire"
          make check-suppressions SUPPRESSION_BASE="--base-ref HEAD~1 --require-base --tripwire"
          make check-layers LAYERS_BASE="--base-ref HEAD~1 --require-base --tripwire"
          make check-design DESIGN_BASE="--shadow-check HEAD~1" DESIGN_ENFORCE=
```

`DESIGN_ENFORCE=` (empty) turns `--enforce` off, so the design step only
reports. Use it in the adoption change and its `main` run, as step 5 explains.
In the next change delete `DESIGN_ENFORCE=` from both lines, so the Makefile
default `--enforce` applies and added gate-capable findings fail the check.

On `main` the `oo` gate also takes `--allow-no-improvement`, which waives the
must-improve rule but still rejects regressions. On a pull request this
repository passes that flag only for `release/*` and `post-release/*`
branches.

## Where State Files Live

All state files sit at the repository root, next to `pyproject.toml`. Commit
them with the code change that causes them.

| Gate | Baseline | Audit log |
|------|----------|-----------|
| `oo` | `.oo-baseline.json` | `.oo-audit.jsonl` |
| `coupling` | `.oo-coupling-baseline.json` | `.oo-coupling-audit.jsonl` |
| `suppressions` | `.suppression-baseline.json` | `.suppression-audit.jsonl` |
| `layers` | `.oo-layers-baseline.json` | `.oo-layers-audit.jsonl` |
| `design` | none | none |

`suppressions` can also write `.suppression-relax.json`, the list of waivers
for the current change. The file formats are in
[Baseline and Audit Formats](REFERENCE.md#baseline-and-audit-formats).

Each run also writes a log under `~/.punt-labs/oo-ratchet/`. See
[Diagnostics and Usage Telemetry](REFERENCE.md#diagnostics-and-usage-telemetry).

## Changing a Baseline Later

`--update` only records scores that are no worse than the base. When a worse
score is the right call, use one of the audited commands. Each one writes an
audit row.

```bash
uv run oo-ratchet oo src/pkg/ --relax src/pkg/model.py --justify "Required API change" --source PL-123
```

```bash
uv run oo-ratchet oo src/pkg/ --rebaseline-files src/pkg/model.py --reason "Required API change" --source PL-123
```

```bash
uv run oo-ratchet coupling src/pkg/ --rebaseline-files src/pkg/model.py --reason "Required API change"
```

```bash
uv run oo-ratchet suppressions src/pkg/ --rebaseline --reason "Counter changed in an upgrade"
```

`--relax` waives named metrics of one file. `--rebaseline-files` records the
named files unless a metric is both over its target and worse than before.
`suppressions --rebaseline` resets the suppression total, the one write that
may raise it. Writes refuse under `GITHUB_ACTIONS=true` without
`--allow-ci-write`. The rules for each are in
[Updating and Making Exceptions](REFERENCE.md#updating-and-making-exceptions).
