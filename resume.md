# Resume: Clean Architecture work

This is the handoff from the machine where the planning was done. Delete this
file in the first PR that finishes wave 1.

## State

- **`main`** includes PR #27 (PL-1685, Done): the OO gate no longer gates
  module shape, `module_size` is a 400-line ceiling, and a branch is judged
  against the merge base. Released? No: vox still pins `punt-oo-ratchet`
  0.4.0, and PL-1717 (B7) ships 0.7.0.
- **The plan** is `docs/clean-architecture-plan.md`: the target model, the
  starting counts, the units, the order and the decisions, with diagrams in
  `docs/architecture/`.
- **Linear epics:**
  - PL-1709: the tool drives Clean Architecture (B1–B7: PL-1711 to PL-1717);
  - PL-1710: this repo moves to Clean Architecture (A0–A5: PL-1718 to
    PL-1723).

  Blocking links are set in Linear.
- **Three decisions on PL-1709 wait for Jim's ratification.** They are
  recommendations, so work can proceed on them.

## Start here: wave 1, three units in parallel

Each unit gets its own worktree and branch. The first commit is a test that
fails on the current code; record the failing and the passing output in the
commit message.

1. **B1, PL-1711: clean layers ratchet.**
   - Today `domain-io` is advisory. It lives in
     `src/oo_ratchet/design/domain_io.py`, and its IO module list is in that
     file and in the README.
   - The `layers` gate is in `src/oo_ratchet/layers/`. It already supports the
     fixed four-layer form and inward-only imports through the design check's
     layer code (`design/layer_config.py`, `layer_edges.py`,
     `layer_violations.py`).
   - Add DomainPurity violations to the layers baseline
     (`.oo-layers-baseline.json`), keyed so a new IO import fails and a
     removed one shrinks the baseline.
   - Start with a failing test: `oo-ratchet layers --check` passes a domain
     module that imports `subprocess`.
2. **A0, PL-1718: measure.**
   - Write the four-ring table for `src/oo_ratchet` in a scratch TOML file, not
     in `pyproject.toml`.
   - Run `uv run oo-ratchet design src/oo_ratchet/ --layers <file> --json`, and
     `uv run python docs/architecture/tools/adopter_shape.py src/oo_ratchet`.
   - Record the counts in the plan's Starting point section and on PL-1710.
3. **B5, PL-1712: average complexity and average params as ceilings.**
   - Add both to `Thresholds.CEILINGS` in `src/oo_ratchet/oo/thresholds.py`.
     Ranking goes through the per-operator badness function, so a ceiling is
     one entry in that set.
   - Start with a failing test: deleting a trivial function counts as an
     `avg_complexity` regression.
   - Demo: `docs/architecture/tools/demo_targets.py` on vox, `main` versus the
     branch. At c825334, 5 vox modules fail a new-file target.

## Commands

```bash
uv sync
make check          # lint, types (mypy strict, pyright), full tests (1307), self-gates
BASE=$(git merge-base origin/main HEAD)
make check-oo check-coupling check-suppressions \
  OO_BASE="--base-ref $BASE --require-base" \
  COUPLING_BASE="--base-ref $BASE --require-base" \
  SUPPRESSION_BASE="--base-ref $BASE --require-base"
make update-oo update-coupling OO_BASE="--base-ref $BASE" COUPLING_BASE="--base-ref $BASE"
```

- **A justified average or stale-row regression:** use
  `uv run oo-ratchet oo src/oo_ratchet/ --relax <file> --justify "<why>" --source <PL-id>`.
  The coupling gate has the same command.
- **Diagrams:** generate the JSON with a script in
  `docs/architecture/tools/`, then show it with
  `lux scene show <id> --from request.json`. The plan's Diagrams section
  gives the request format.

## Lessons from the planning machine

- **Average metrics punish good moves.** Each change in PR #27 that deleted
  simple functions or added real decisions needed an audited `--relax` on
  `avg_complexity` or `avg_params`. B5 removes this; do it early.
- **LCOM ignores calls from one method to another.** A new method that only
  calls other methods counts as disjoint and worsens class cohesion. Make
  such helpers static, or have them read shared state directly.
- **Stale baseline rows exist on `main`:** for example the coupling rows for
  `oo/__init__.py` and `writer.py`. When a touched file "regresses", check
  the score on unchanged `main` before blaming the change.
- **pytest's temp directory can sit inside a git checkout** (the workspace
  `.tmp`). A test that needs "not a git repo" must set
  `GIT_CEILING_DIRECTORIES`.
- **Remote review:**
  - Devin Review re-reviews every push and finds something most rounds. Fix
    what is real, and answer wording-only preferences with a reason.
  - Qodo reviews at open. Close its findings with
    `qodo pr-review-session mark-implemented` or `dismiss`.
  - `gh event listen` is not enabled for this account, so poll the PR with a
    3-minute cron loop.
- **Local review** (`code-reviewer`, `silent-failure-hunter` and
  `qodo review`) found two real regressions in PR #27 before the PR opened.
  Keep running it before every push.

## Cleanup on the planning machine (optional)

- The worktrees `.claude/worktrees/pl-1685-shape-metrics` and
  `.claude/worktrees/init-claude-md` hold branches that are already merged.
- The `tests/lux/` files are never collected by pytest, and some reference
  removed metrics. They should be deleted or brought into the suite; this is
  not yet filed in Linear.
