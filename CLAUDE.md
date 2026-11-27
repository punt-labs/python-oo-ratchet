# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`punt-oo-ratchet` (PyPI) ships one CLI, `oo-ratchet`, that runs quality gates
over a Python package. A "ratchet" here is a gate that compares the current
source against a committed baseline (or a base-commit scan) and fails if
quality got worse:

- `oo`: must-improve. No OO metric regresses on a touched file and at least
  one improves. State: `.oo-baseline.json`, `.oo-audit.jsonl`.
- `coupling`: regression-only. State: `.oo-coupling-baseline.json`,
  `.oo-coupling-audit.jsonl`.
- `suppressions`: regression-only on the total `noqa` / `type: ignore` /
  `pylint: disable` / `pyright: ignore` / per-file-ignores count, compared to
  a fresh scan of the base tree. State: `.suppression-baseline.json`,
  `.suppression-audit.jsonl`.
- `layers`: a baseline of forbidden import edges that may only shrink. State:
  `.oo-layers-baseline.json`, `.oo-layers-audit.jsonl`. The four-ring table
  (entry/adapters/application/domain) is `[tool.oo-ratchet.layers]` in
  `pyproject.toml`; `make check-layers` runs the gate.
- `design`: advisory; findings exit 0, bad input exits 2. `--shadow-check REF`
  compares findings against the merge base. No state files.

All state files live at the repository root.

`README.md` is the user-facing specification of every rule, metric and flag;
read the section for the gate you are changing before changing it. The formal
model is `docs/ratchet.tex`. The policy enforced is punt-kit's
`lang-rules/python/python-oo-adoption.md`.

## Workflow

`docs/WORKFLOW.md` is how work moves here: Linear backlog, one PR per unit,
local review, a demo through the `oo-ratchet` CLI, the merge gate, and the
close-out with a beadle recap email, a vox notice and lux tables. Read it
before writing code.

@docs/WORKFLOW.md

## Commands

Always use `make` targets; Python 3.13+, managed by `uv`.

```bash
uv sync
make check            # lint type test check-oo check-coupling check-suppressions
                      # check-layers
make lint             # ruff check + ruff format --check (src tests evals)
make type             # mypy --strict on src+tests, pyright on tests+evals,
                      # plus a separate mypy run per evals/design/*/{bad,good}
make test             # full suite: pytest -m "" (includes real-git `slow` tests)
uv run pytest tests/test_oo_cli.py::TestOptionsParse -m ""  # one class
uv run pytest -m slow                     # only the real-git tier
uv run pytest tests/test_design_evals.py  # design eval harness
```

Tests marked `slow` (module-level `pytestmark`) drive real throwaway git
repositories through `GitSandbox` in `tests/conftest.py`. An autouse fixture
points `HOME` at a scratch directory so the CLI's log and telemetry never touch
the real home directory. Every test file under `tests/` is collected by pytest;
there is no uncollected test directory.

## The package ratchets itself

`make check-oo`, `check-coupling`, `check-suppressions` and `check-layers` run this package's
own gates over `src/oo_ratchet/` only (not `tests/` or `evals/`). Without
`--base-ref`, `check-oo` and `check-coupling` compare the working tree against
the merge base of `origin/main` and `HEAD`, so on a clean `main` they see no
touched files and pass trivially. Uncommitted edits to tracked files are
checked; a new, untracked module is not checked until it is staged. To
check a branch exactly as CI does, get the merge-base SHA with
`git merge-base origin/main HEAD`, then:

```bash
make check-oo OO_BASE="--base-ref <sha> --require-base"
make check-coupling COUPLING_BASE="--base-ref <sha> --require-base"
make check-suppressions SUPPRESSION_BASE="--base-ref <sha> --require-base"
make check-layers LAYERS_BASE="--base-ref <sha> --require-base"
```

Consequences for any change under `src/oo_ratchet/`:

- No OO metric may regress on any touched file, and at least one metric must
  improve on at least one touched, already-baselined file (other touched files
  may stay level). New files must meet the targets below; a change that only
  adds files passes by meeting them, with no improvement needed elsewhere.
  After editing, run `make update-oo` and `make update-coupling` (with the
  same `--base-ref`) and commit the rewritten baseline and audit files with
  the source change. `--check` requires the in-tree baseline to equal the current
  scores.
- `check-layers` fails on a layer-import edge not in `.oo-layers-baseline.json`
  (the four-ring table is `[tool.oo-ratchet.layers]` in `pyproject.toml`; the
  baseline holds 106 edges at adoption). Edges may only be removed: after
  removing one, run `make update-layers` and commit the rewritten baseline and
  audit file. Adding an edge or widening the table needs
  `--update --allow-config-change --source <ref>`.
- `check-suppressions` compares the total suppression count (`noqa`,
  `type: ignore`, per-file-ignores, ...) with the base tree's total. Adding one
  fails the gate unless the same change removes another.
- On a pull request, CI passes `--allow-no-improvement` to the OO gate only
  for `release/*` and `post-release/*` branches. On pushes to `main` it runs
  every gate with `--base-ref HEAD~1 --require-base --tripwire`, and the OO
  gate also with `--allow-no-improvement`.
- Loosening is only through audited operations (`--relax FILE --justify`,
  `--rebaseline-files PATHS --reason`, `--rebaseline`). Writes refuse under
  `GITHUB_ACTIONS=true` without `--allow-ci-write`.

OO targets new code must meet, all eight (`src/oo_ratchet/oo/thresholds.py`,
tabled in `README.md` under "Targets and counting rules"): encapsulation ratio
>= 1.0, average params <= 4, max complexity <= 10, average complexity <= 5,
at most 400 code lines per module, no explicit `__init__` on non-dataclass
classes, no public `self.x` assignments, and `from __future__ import
annotations` in every module. Module size, average params and average
complexity are ceilings: a move that stays at or under the target is neither a
regression nor an improvement. Module shape (classes per module,
methods versus functions) is not gated; keep cohesive code together rather
than splitting it to shrink files. Classes here construct in `__new__` with
private, class-level-annotated `_fields` instead of `__init__`. Follow that
pattern.

## Architecture

- `__main__.py`: `Dispatcher` takes the first argv word, looks it up in
  `gates.py`'s `GATES` dict (`oo`, `coupling`, `suppressions`, `design`,
  `layers`), configures the diagnostic log (`logging_config.py`, via
  `punt-observe`), wraps the run in a usage event (`usage.py`), and calls the
  gate's `cli.main(argv)`. Adding a gate means adding it to `GATES` and to
  `Dispatcher.USAGE`.
- Each gate is a subpackage with a recurring shape: `cli.py` (argparse
  `Options` and `main`), `scorer`/`scanner`/`metrics` (measure the tree),
  `baseline.py` (read/write the JSON snapshot), `gitio.py` (read the base
  commit's blobs and baseline via git), `ratchet.py` or `compare.py` (decide the
  verdict), `writer.py`/`bless.py`/`relax.py` (the audited write operations),
  `audit.py` (append to the `.jsonl` log), `outcome.py`/`report.py` (render).
- In `oo/`, `thresholds.py` holds the targets and the comparison order:
  each metric ranks values by a badness function, and a ceiling metric
  (`module_size`, `avg_params`, `avg_complexity`) ranks every value under its
  target the same.
  `backfill.py` (top level) adds missing baseline rows on scoped `--update`.
- `design/` is the advisory scanner: rule modules (`*_rules.py`,
  `middle_man.py`, `tag_switch.py`, `misplaced_rule.py`, `domain_io.py`,
  `layer_*`) emit findings over a syntactic project-class index
  (`project_types.py`, `receiver_*`); `shadow*.py` implements
  `--shadow-check` by scanning the merge base in a detached temporary worktree
  and comparing finding multisets keyed by `(rule, module, symbol)`.
- `layers/` turns `design`'s layer rules into a baselined gate; it imports
  `design/layer_config.py`, `layer_table.py`, `layer_edges.py`,
  `layer_violations.py` and `modules.py` rather than duplicating them.
- Source selection is shared by all gates: `source_options.py` parses
  `--namespace` and the `[tool.oo-ratchet]` `namespace`/`roots` config;
  `source_set.py` and `sources.py` join several physical roots of one PEP 420
  namespace into a single scan; `source_history.py`, `source_archive.py` and
  `source_rescan.py` reproduce the same selection at a base commit (with git
  rename pairing). Baseline keys are always repository-relative physical
  paths; import identity is the namespace plus the dotted module key.
- stdout carries only gate reports and `--json` output; diagnostics go to
  `~/.punt-labs/oo-ratchet/logs/oo-ratchet.log`, warnings and errors also to
  stderr. Do not use `print` (`T20` is enforced in `src/`).

## Gate behavior to preserve

- Fail closed: unreadable comparison state, git errors, parse errors and
  unresolvable bases fail the gate (or exit 2), never pass silently.
- Unknown config keys, metrics or modes in `[tool.oo-ratchet.*]` are errors.
- Baseline/audit file names and formats are a compatibility contract with
  adopter repos (vox, quarry, lux, z-spec) that switched over without
  rebaselining; the formats are documented in `README.md`.

## Design evals

`evals/design/<case>/` holds paired `bad/loans` and `good/loans` packages, a
shared `behavior.py`, and `expected.toml` listing the `(rule, path, symbol)`
findings the design scanner must report. `tests/test_design_evals.py` checks
recall, precision and ordering. A known false positive stays a strict
`xfail`; do not change a fixture to hide it. Every variant uses the package
name `loans`, which is why `make type` runs mypy once per variant.

## Release

On a `release/vX.Y.Z` branch, bump `version` in `pyproject.toml` and move the
`CHANGELOG.md` entries under it; after that PR merges, push the `vX.Y.Z` tag.
`.github/workflows/release.yml` refuses a tag that does not match
`pyproject.toml`, then builds, publishes to TestPyPI, verifies that wheel, and
publishes to PyPI.

@.punt-labs/beadle/CLAUDE.md
@.punt-labs/vox/CLAUDE.md
