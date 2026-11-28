# Layers Gate Reference

The `layers` gate in full: what it checks, how it
builds a starter table, and what it counts as an import. For a first
setup, start with [Configuring a Repo](CONFIGURING.md).

**Contents**

- [What the Gate Checks](#what-the-gate-checks)
- [Starter Table From suggest](#starter-table-from-suggest)
- [Domain Purity Edges](#domain-purity-edges)
- [JSON Output](#json-output)
- [Adopting Domain Purity Edges](#adopting-domain-purity-edges)
- [What the Gate Counts as an Import](#what-the-gate-counts-as-an-import)

## What the Gate Checks

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
- `--check` also fails when a layer's `imports` widens against the base config, or, with the fixed four-layer form on both sides, when a module present at both the base and the current tree is assigned to an outer layer than at the base (ring order entry, adapters, application, domain) or loses its layer (leaving `domain` is always outward). A module absent at the base is not a move: it is not compared, and its edges are not judged under the base config, only against the current config and the baseline. For a single positional package directory, the base's modules are the tracked `.py` files of the base commit (`git ls-tree`, so `export-ignore` and stray non-UTF-8 file names elsewhere do not matter, and a base holding only an `__init__.py`, or none, is fine), named by the same rule as the working tree. The base package is found at the same directory (a root package included), or, when that directory has no tracked Python at the base, by import name among the top-level packages (a directory under another regular package does not count): one match is the package moved to another directory, more than one fails the check with a message naming them instead of guessing, and none means the package is new and has nothing to compare. A `--namespace` or multi-root selection is not reconstructed from history: every current module counts as present, which is stricter, so a new module listed in an outer layer by name needs `--allow-config-change`. Moving a module toward `domain` is not widening, and declared layers compare `imports` only. With no layer config at the base, or no base ref, no move is checked. Land that as its own reviewed change with `--allow-config-change` (accepted with `--check` or `--update`; `--update` records `config_change` in the audit entry).
- `--update` writes the baseline atomically (temp file, then rename) and restores the previous one if the audit entry cannot be written. A package with no rows is adopted on `--update`; `--check` accepts that when the package does not exist at the base, and fails if an existing package gained rows. `--update` also drops rows of packages whose directory no longer exists in the repository, and records them as `retired` in the audit.
- `--base-ref`, `--require-base` and `--tripwire` are accepted only with `--check`; `--allow-ci-write` and `--source` behave as for coupling.

## Starter Table From suggest

`oo-ratchet layers src/pkg/ --suggest` prints a starter fixed-form `[tool.oo-ratchet.layers]` table, three lists and a summary line. It never guesses a ring: a ring comes from intent someone wrote down, and import evidence can only refuse that intent. It needs no existing layers table, writes no file, and never touches `pyproject.toml` or the baseline: **the table is never applied automatically**, because a wrong ring silently passes forbidden imports. Review every reason, then copy the table in yourself. The output is valid TOML (all notes are comments) and always exits 0; it is sorted, so two runs print the same text. Names and reasons are printed with control characters and line breaks escaped, so a file name holding a newline cannot start an active TOML line when you paste the table.

Ring intent comes, in this order, from:

1. A declaration. Either a module-level string constant `__ring__ = "domain"` (one of `entry`, `adapters`, `application`, `domain`; read from the syntax tree, the module is never imported; a value that is not a string literal, or not a ring name, leaves the module unclassified with that reason), or an existing fixed-form `[tool.oo-ratchet.layers]` table. If both exist and disagree, the module is unclassified and the reason says so.
2. A package name. Any dotted name below the package root that is `domain`, `model`, `models` or `core` suggests `domain`; `application`, `usecases` or `use_cases` suggests `application`; `adapters`, `adapter`, `infra` or `infrastructure` suggests `adapters`. Names that suggest different rings (`infra.domain.x`) give no ring. A `[tool.oo-ratchet.suggest]` table replaces the names of a ring: `domain = ["logic"]`, `application = [...]`, `adapters = [...]`; any other key, or a value that is not a list of names, is a failure (exit 1).
3. Otherwise the module is unclassified, and its line shows its evidence (what IO it reaches).

The one ring taken from evidence is `entry`: a module that imports `argparse` or `typer` (not under `if TYPE_CHECKING:`), or is a `[project.scripts]` target of the nearest `pyproject.toml`. The package root is placed in `entry` whatever it imports, as vox, lux and z-spec place theirs; it is unclassified when a non-entry module imports it or it has a relative import climbing above the package.

Evidence refuses intent in these cases, and each is printed as a `CONFLICT` with its path instead of a ring:

- A module whose intent is `domain` and that reaches IO, directly or through the modules it imports, is never suggested `domain`. The reason names the chain, for example `pkg.domain.m -> pkg.helper -> pkg.store -> open()` (a bare `open`, `builtins.open` and a literal dynamic import count as IO, as in the gate's purity edges; the chain is the shortest and a cycle cannot loop).
- A module whose intent disagrees with entry evidence (a `domain` package that imports `argparse`).
- After that, a `domain`, `application` or `adapters` module that imports a module of a ring it may not (the gate lets `domain` import only `domain`, `application` only `application` and `domain`, `adapters` anything but `entry`) is a conflict naming the edge; a `domain` or `application` module that imports a module with no ring is unclassified. This repeats until nothing changes.

Output is the header, the table, then: `# Ring from declaration, name or entry evidence:`, `# Conflicts:`, `# Unclassified:`, and a `# Summary:` count line. Every listed line carries its reason in parentheses; an empty list says `none`. Conflicts and unclassified modules are left out of the table, so `--check` reports them as unassigned until you place them. That includes a module name shared by several files (`pkg/a.py` and `pkg/a/__init__.py`): the gate sees one module, so the name is one unclassified entry listing every file. Imports are read with the gate's own edge extractor: re-exports through a package `__init__`, literal dynamic imports and `TYPE_CHECKING` imports count as they do for `--check`. Every `[project.scripts]` name that targets a module appears in its reason. A malformed `[project.scripts]` (not a table, or a value that is not a `module[:object] [extras]` entry point) is a one-line failure (exit 1); with no `pyproject.toml` the header says console scripts were not read. `--suggest` needs no git repository and starts no git process. Lists hold explicit module names (`[`, `*` and `?` in a name are escaped, since the gate matches entries as globs), except where a prefix is exact: `pkg.sub` and `pkg.sub.*` appear only when every module at or under `pkg.sub` has that ring (the glob also claims modules added later under it). `--suggest` cannot combine with `--check`, `--update` or `--json`.

## Domain Purity Edges

With the fixed four-layer form, the gate also baselines domain purity: each IO module a `domain` module imports (the `domain-io` list in the design check, `TYPE_CHECKING`-only imports excepted) is an edge from that module to the IO module, for example `pkg.domain.model -> subprocess`, and a bare unbound `open(...)` call or a `builtins.open(...)` call (also through `import builtins as b`) or `from builtins import open` is an edge to `builtins.open`. A file-system method called on a `Path` object (`read_text`, `exists`, `iterdir`, `mkdir` and the rest of the list under "Path file IO" in [DESIGN.md](DESIGN.md)) is an edge to `pathlib`, even when the `Path` import is `TYPE_CHECKING`-only; the receiver must be evidenced as a `Path` in the module (an attribute only on `self`, `cls` or as a path's `.parent`; `list[Path]` elements, loop variables and unpacking are not followed), and a `read_text` on any other object is not an edge. A literal `importlib.import_module("subprocess")` or `__import__("socket")` is an edge to that IO module too; none of these count under `if TYPE_CHECKING:`, and a name inside the scanned package is never IO even when the package is called `rich` or `json`. A failure that lists a purity edge names the way out: a port in the application layer implemented in an adapter, or the one-time `--allow-config-change` update (see
[Adopting Domain Purity Edges](#adopting-domain-purity-edges)). A new one fails `--check`; a removed one is a stale baseline entry that `--update` drops. Declared layers have no domain and no purity edges.

## JSON Output

`--json` prints one object. The keys `modules` (count), `violations` (each `source`, `target`, `source_layer`, `target_layer`) and `unassigned` (module names) are unchanged. Three keys draw a diagram from the output alone:

- `module_rings`: each module's ring, a map from dotted module name to the layer name the config assigns (`entry`, `adapters`, `application`, `domain` in the fixed form; the declared name otherwise). A module no layer claims maps to `null`. The package root is listed only when a layer claims it.
- `ring_edges`: a list of `{"source_ring", "target_ring", "count"}`, sorted, one row per pair of rings with violating layer edges. The count is edges (one per importing and imported module), not import sites, so it is smaller than the design check's `layer-import` count. Domain-purity edges are not counted here, so the `ring_edges` counts plus the `io` rows of `marked_violations` equal the baselined edge count the gate reports (on this repo: 23 + 7 = 30).
- `marked_violations`: every violation, in `violations` order, as `{"source", "target", "source_ring", "target_ring", "kind"}`. `kind` is `layer` for a layer edge and `io` for a domain-purity edge (the target ring is `io`).

## Adopting Domain Purity Edges

An adopter whose domain modules already import IO adopts these edges once: run `oo-ratchet layers src/pkg/ --update --allow-config-change --source <ref>` and commit the baseline. CI runs `--check --allow-config-change` with the merge-base `--base-ref` in that PR, and the post-merge `push: [main]` run of that one merge commit also passes `--allow-config-change` (`--check --base-ref HEAD~1 --require-base --tripwire --allow-config-change`), because `HEAD~1` lacks the edges; drop the flag from both once it has merged. With the flag, `--update` may add edges whose layer class is `io` (the audit entry lists them under `added` next to `config_change`), and `--check` does not count them as baseline growth over the base or as violations under the base config. Any other new edge is still refused with the flag. Without the flag nothing changes: such an update is refused and such a check fails.

## What the Gate Counts as an Import

The gate over-approximates: it must never pass a forbidden import, and a rare false positive is fixed by restructuring. Edges counted: imports anywhere in a module (functions included) and `TYPE_CHECKING` imports (as in the design check).

- **Re-exports.** `from pkg import X` is an edge to every module the package's `__init__` imports `X` from, on any path: an import anywhere in the `__init__` counts (module scope, any block, function bodies, `import a.b as X`), and rebinding, `del`, annotations, `with ... as X` or `__all__` never remove it. A wildcard `from M import *` in an `__init__` makes every name imported from that package an edge to `M` as well, transitively through chained wildcards.
- **Dynamic imports.** Any call anywhere in a module (body, function bodies, defaults, decorators, class bodies, lambdas) whose callee's final name or attribute is `import_module` or `__import__`, with a literal string name (positional or `name=`; a relative name resolved with a literal `package`), is an edge when the name is a module of the scanned package. There is no binding analysis: a method of an unrelated object called `import_module` is a deliberate false positive, and so is a call after the name was rebound. Names aliased with `from importlib import import_module as x` or `x = importlib.import_module` count in any scope.
- A relative import that climbs above the package root fails the check ("unresolvable relative import", with file and line). Computed module names and attribute access on an imported package (`import pkg; pkg.a.f()`) are out of scope.
- Git failures (`ls-files`, `ls-tree`) fail the gate closed. Retired-row detection reads the working tree, so an unstaged deletion retires. The audit log is appended with one write per record and cut back on failure; the baseline is replaced atomically and keeps its file mode (0644 for a new file).

This repository runs `layers` on itself: `make check-layers` and its CI step read the table in `pyproject.toml`. [Adopting Clean Architecture with oo-ratchet](CONFIGURING.md#adopting-clean-architecture-with-oo-ratchet) walks through the whole path.
