# Changelog

## [Unreleased]

## [0.4.0] - 2026-11-22

### Changed

- Shadow scans preserve symlink package spelling for layer matching and stable
  keys in both the merge-base and working-tree scans.
- Shadow merge-base checkout allows 300 seconds without changing the default
  timeout of other Git calls. Owned temporary files and worktree registrations
  are cleaned up after checkout timeouts, errors, or interrupted scans.
- Design scans retain files whose module names collide with packages instead of
  silently replacing them. Shadowed files receive stable source-relative keys;
  plain reports retain both paths and layer rules apply to both files.
- Shadow comparisons preserve finding multiplicity for stable design keys:
  repeated keys count as additional debt instead of being silently deduplicated.
  Added/removed lists repeat keys for each changed occurrence.
- `domain-io` is purely import-based, including os, os.path, pathlib, io,
  tempfile and glob, with TYPE_CHECKING imports exempt and findings keyed by
  the imported module. Domain code reaches the filesystem and environment
  through an injected port. Bare `open` calls fire only when no binding of that
  name occurs anywhere in the module; flow-sensitive alias analysis is removed.

### Added

- Shadow-mode `design <src> --shadow-check <git-ref> [--layers FILE] [--json]`
  compares a merge-base scan to the working tree using stable, line-independent
  design keys and the existing OO per-file comparisons. Ordered Tier 0/Tier 1
  debt checks bound repository-wide trades; no weighted sum, rename matching or
  baseline file is used. Deterministic text/JSON reports remain advisory (exit 0
  for every verdict, exit 2 for input errors); adopter gates and releases are
  unchanged.
- Advisory `primitive-params`, `tag-switch`, `middle-man`, `split-cohesion` and
  Tier 0 `size-cap` checks, using syntactic signatures, explicit project classes
  and LCOM4 components. Initializers are excluded from cohesion; layer-specific
  exemptions are documented. All seeded rule expectations are active, including
  the approved extra primitive finding for bad tag-switch and module cap for
  bad god-class. Findings still exit 0; adopter gates and thresholds are unchanged.
- Advisory `envied-data`, `feature-envy`, `data-clump` and `misplaced-function`
  checks using explicit syntactic receiver types and deterministic maximal
  shared-name intersections. They run without layer configuration, excluding
  entry/adapters when configured. Their eval expectations are now active;
  fixtures are unchanged. Findings still exit 0; adopter gates are unchanged.
- Optional strict `[tool.oo-ratchet.layers]` configuration and `design --layers`
  override, with advisory layer-import, domain-io, unlayered-module and thick-entry
  checks. Layer eval expectations now run without future-rule xfails. Findings
  still exit 0; adopter ratchet gates are unchanged.
- Seeded library-loan design eval pairs with behavior equivalence, finding-key
  recall/precision and ordering checks, and strict future-rule xfails.
- `make lint` and `make type` (hence `make check`) now also cover `evals/`.
  Design rules and ratchet gates on `src/` are unchanged.

## [0.3.1] - 2026-11-19

### Fixed

- Scoped OO and coupling `--update` now backfill and report missing baseline rows throughout the requested source tree, including committed files outside the diff and untracked files. Existing untouched rows and rename regression checks are preserved.
- Backfilled rows are recorded separately in the audit log, without synthetic metric deltas or improvement counts. Touched new files retain their existing accounting.

## [0.3.0] - 2026-11-18

### Changed

- **Behavior change (PL-1141):** a suppression waiver in `.suppression-relax.json` now only waives the change that adds it. Once the entry is on the comparison base (the merge-base, or `HEAD~1` for the post-merge tripwire) unchanged, it is retired and covers nothing. Before, a merged ceiling stayed live, so after a cleanup lowered a file's count, suppressions could grow back up to the old ceiling without a new waiver, and a ledger-only PR could pre-authorize future growth. A new rise in a file with a retired entry needs a fresh `oo-ratchet suppressions --relax FILE --justify ...`, which rewrites the entry. Retired entries can be deleted from the ledger.
- An unparseable `.suppression-relax.json` on the comparison base now fails the check.
- **Behavior change:** `module_size` now counts only lines that carry code. Docstrings (module, class and function), comments and blank lines no longer count; before, every non-blank line did. Every module's `module_size` drops (and many modules' `classes_per_module`), so committed `.oo-baseline.json` rows go stale: the OO check fails a touched file whose row no longer matches its score until the row is refreshed. When bumping to 0.3.0, refresh every row once with an audited `oo-ratchet oo SRC --rebaseline-files <every baselined file> --reason "adopt 0.3.0 counting"`; the refresh only lowers values, so nothing is loosened. The 300-line cap now applies to code lines.
- **Behavior change:** `classes_per_module` no longer counts exception classes (a base of `Exception`/`BaseException`, a name ending in `Error`/`Exception`/`Warning`, or an exception defined earlier in the module), enums (`Enum`, `IntEnum`, `StrEnum`, `Flag`, `IntFlag`, `ReprEnum`) or `@dataclass` classes, alongside the `Protocol`/`TypedDict` it already skipped. `class_to_func_ratio` still counts them. A module of only such classes now has `classes_per_module = 0`, which also makes a new extracted module of that shape eligible for the zero-class extraction carve-out.
- **Behavior change:** the default `efferent_coupling` limit is 10 (was 7). `__main__.py`'s 15 and `[tool.oo-ratchet.coupling.caps]` overrides are unchanged. This is a deliberate policy loosening in the package default, not an audited per-repo operation: no baseline rows change, and modules with 8-10 internal imports now pass. Adopters whose written rules say 7 (punt-kit's PL-CU-1 and the copies in lux, z-spec and vox) should update them to 10 when they bump, and can drop any cap at or below 10.
- Suppression waiver timestamps (`added_at`) now carry microseconds, so a re-relax within the same second never matches a merged entry.

## [0.2.3] - 2026-11-18

### Fixed

- Coupling `--rebaseline` audit entries now count `files_improved` (a file with a gain and no regression) and `files_regressed`, where before both were always 0.

## [0.2.2] - 2026-11-18

### Fixed

- `stateless-values = "any"` is a superset of the default exemptions again: a `@dataclass` or `__slots__ = ()` marker that stores no instance state stays exempt even when it mutates host collections (regressed in 0.2.1).
- `--rebaseline-files` (OO and coupling) records the metrics it improved in a new audit field, `improved`, as well as the regressions it waives in `deltas`. `improved` is audit-only and never read back as a waiver.
- Coupling `--rebaseline` records every changed metric as `deltas` and saves `--reason` in its audit entry.

## [0.2.1] - 2026-11-18

### Fixed

- `stateless-values = "any"` now counts in-place writes to private collections (`self._x[k] = v`, `+=`, `del`, and mutator calls such as `self._x.append(...)` / `.update(...)`) as private state, so those classes are no longer exempted from LCOM. A mutator-named call on any private attribute counts, collection or not (`self._client.update(...)` too): a class holding a private dependency has instance state.

## [0.2.0] - 2026-11-18

### Added (ported from lux)

- `[tool.oo-ratchet.coupling] stateless-values = "any"`: LCOM skips every class that writes no private `self._*` state, counting `object`/`super()`/`type(self)` `.__setattr__` writes as state.
- `[tool.oo-ratchet.coupling.caps]`: per-file metric caps keyed by exact repository-relative path, used by `--check`, the per-file report and the bless gate.
- `oo-ratchet coupling --rebaseline-files PATHS --reason TEXT`: bounded, audited bless of named files; refuses a metric that is both over its cap and regressed against the base-committed baseline.

- `oo-ratchet suppressions --rebaseline --reason TEXT [--source REF]`: audited reset of the suppression baseline to the current counts, the one write allowed to raise the total, e.g. after adopting a package version that counts differently (PL-1175).

### Changed

- LCOM's stateless-value check no longer looks inside nested classes, in either mode: an inner class's `self` stores don't block exempting its parent.
- The summary grades (and exit code) judge a capped file against its cap and `__main__.py` against its relaxed table, so they agree with the per-file report.

## [0.1.0] - 2026-11-18

### Added

- Published to PyPI as `punt-oo-ratchet` (CLI `oo-ratchet`) via `release.yml` trusted publishing.

### Fixed (Qodo review of #1)

- `--tripwire` on all three gates, and it fails when main has no baseline.
- Coupling: `from pkg import mod`, relative imports in `__init__.py`, nested-package efferent coupling; audit records removed paths.
- Git paths with non-ASCII names are no longer dropped from the diff.
- Extraction provenance counts repeated lines (multiset overlap).
- Suppressions: PEP 263 coding cookies, file-level directives (`# ruff: noqa`, leading `# type: ignore`, ...), `.` targets.
- Non-object audit lines raise the gate's audit error; single-file OO targets record an error row.
- `--rebaseline-files` resolves relative paths against the repo root.

### Added

- `oo-ratchet` package and CLI (`oo-ratchet {oo,coupling,suppressions}`), extracted from vox's `tools/` ratchets.
- Extraction provenance for new zero-class modules, coupling `--tripwire`, `tokenize`-based suppression scan (from quarry).
- `--rebaseline-files` bounded bless with over-cap carry, vanished-row cleanup, removed rows in the audit log (from lux).
- Order-independent (Tarjan) import-cycle detection; `BaseModel`, `@dataclass` and empty-`__slots__` classes exempt from LCOM (from lux).

### Fixed

- The OO scorer reports unreadable or non-UTF-8 files as error rows instead of crashing (PL-778).
