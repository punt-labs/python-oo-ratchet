# B7 adopter dry runs (PL-1717)

Read-only dry runs of this checkout (origin/main `e887af7`, version 0.6.0,
the code that becomes 0.7.0) against vox, quarry, lux and z-spec. Each adopter
was cloned with `git clone --local` into `.tmp/adopters/<name>` of this
worktree; nothing was run inside the originals. The new version ran as
`uvx --from <this worktree> oo-ratchet`; the old version as
`uvx --from punt-oo-ratchet==<pin> oo-ratchet`.

Adopter commits tested: vox `60baa52`, quarry `60bfe37`, z-spec `6545a90`,
lux `bae8d6d3` (the local HEAD of each checkout).

## Adopter setup today

| Adopter | Pin | State files | Source passed to the gates | CI form |
| --- | --- | --- | --- | --- |
| vox | `punt-oo-ratchet==0.4.0` | `.oo-*`, `.oo-coupling-*`, `.suppression-*`, `.suppression-relax.json` | `src/punt_vox/` | `make check-oo/coupling/suppressions` with `--base-ref <merge-base> --require-base` on PRs; on main `HEAD~1 --require-base`, and `--allow-no-improvement` on the OO gate. `design --shadow-check origin/<base>` |
| quarry | `==0.4.0` | same three sets | `src/quarry/` | PR as vox. Main: `check-oo HEAD~1 --require-base` (no `--allow-no-improvement`), coupling adds `--tripwire`. Also `oo --audit-completeness`. `design --shadow-check` |
| z-spec | `==0.4.0` | same three sets | `src/punt_zspec/` | PR as vox. Main: OO gate with `--allow-no-improvement`. `design --shadow-check ... --json` |
| lux | `==0.6.0` | same three sets, plus its own `.layer-baseline.json` from `tools/layer_contract.py` | two source sets: `--namespace punt_lux src/punt_lux packages/punt-lux-client/src/punt_lux` and `--namespace punt_service packages/punt-service/src/punt_service` | `ratchets.yml`: `make check-oo BASE_REF=<before-sha>` (no `--allow-no-improvement` on the lux set), `check-coupling`, own `check-layers`. `design --shadow-check` |

All four have a `[tool.oo-ratchet.layers]` table in `pyproject.toml` (fixed
four-ring form). None has an `.oo-layers-baseline.json` yet. Lux also has
`[tool.oo-ratchet.coupling]` and `.caps`, which 0.7.0 parses without error.

## (b) oo, coupling, suppressions `--check`

Three base settings per gate: no base (merge-base default), `--base-ref HEAD~5
--require-base`, `--base-ref HEAD~25 --require-base`. Exit codes, old / new.
Lux is listed per source set (lux set / service set).

| Adopter | Gate | no base | HEAD~5 | HEAD~25 |
| --- | --- | --- | --- | --- |
| vox | oo | 0 / 0 | 0 / 0 | 0 / 0 |
| vox | coupling | 0 / 0 | 0 / 0 | 0 / 0 |
| vox | suppressions | 0 / 0 | 0 / 0 | 0 / 0 |
| quarry | oo, coupling, suppressions | 0 / 0 | 0 / 0 | 0 / 0 |
| z-spec | oo | 0 / 0 | **0 / 1** | 0 / 0 |
| z-spec | coupling, suppressions | 0 / 0 | 0 / 0 | 0 / 0 |
| lux | oo | 0 / 0 | **0 / 1** (lux set), 0 / 0 (service) | 1 / 0 (lux), 1 / 0 (service) |
| lux | coupling | 0 / 0 | 0 / 0 | 1 / 1 (lux), 0 / 0 (service) |
| lux | suppressions | 0 / 0 | 0 / 0 | 0 / 0 (lux), 1 / 1 (service) |

Lux HEAD~25 failures that are the same in both versions: coupling regressions
on the lux set, and `base commit predates the scanned source tree` on the
service set. They are not differences.

Every difference in a verdict is one case: the old gate passed, the new gate
prints `FAIL: no metric improved on any touched file`. Cause: `avg_params`,
`avg_complexity` (and `module_size`) are ceilings in 0.7.0 (PL-1712, PL-1685).
A change that only moves them under their target is neither a regression nor
an improvement. Example, z-spec HEAD~5:

```text
src/punt_zspec/commands/enablement.py    avg_complexity   1.320   1.270   -0.050   PASS      (old: IMPROVED)
src/punt_zspec/lux/subscription.py       avg_params       0.900   0.820   -0.080   PASS      (old: IMPROVED)
FAIL: no metric improved on any touched file                                                 (old: PASS)
```

All other output differences are the removal of the `method_ratio`,
`classes_per_module` and `class_to_func_ratio` rows (PL-1685) and `RELAXED` /
`IMPROVED` becoming `PASS` for ceiling metrics under target. No baseline or
audit file failed to load; no run changed a state file. This is documented in
the CHANGELOG, so these are behaviour changes, not bugs.

### How often it bites: replay of each adopter's last 15 commits

For each commit, `oo --check --base-ref HEAD~1 --require-base` (the main-push
form), old pin vs new:

| Adopter | Commits that pass old and fail new | Failure text |
| --- | --- | --- |
| vox | 0 of 15 | |
| quarry | 1 of 15 (`f574d91`, only `enablement.py module_size` 54 to 52) | no metric improved |
| z-spec | 4 of 15 (`6545a90`, `259fb7f`, `816841c`, `f87c8dd`) | no metric improved |
| lux | 2 of 15 (`6598d7f8`, `4240b6dd`) | no metric improved |

Impact by CI form: vox and z-spec main-push runs pass `--allow-no-improvement`,
so only their PR runs see it. Quarry and lux main-push runs do not, so those
would go red. An adopter PR that only trims an under-target module needs a
real improvement elsewhere in a touched file, or a hunk that lowers a
non-ceiling metric (`encapsulation_ratio`, `max_complexity`, the violation
counts) in a touched file.

## (c) layers

`layers --check` with no baseline exits 1 on all four (expected: no baseline).
`layers --update --allow-config-change --source b7-dry-run` on the copies:

| Adopter | Modules | Unassigned | Violations | layer | io | Result of `--update` |
| --- | --- | --- | --- | --- | --- | --- |
| vox | 632 | 149 | 168 | 146 | 22 | refused: package not covered |
| quarry | 494 | 7 | 295 | 275 | 20 | refused: package not covered |
| z-spec | 63 | 0 | 25 | 22 | 3 | wrote `.oo-layers-baseline.json` and `.oo-layers-audit.jsonl`; `--check` then PASS (63 modules, 25 baselined) |
| lux | 977 | 14 | 171 | 159 | 12 | refused: package not covered |

Ring edge counts (source ring to target ring):

| Adopter | adapters to entry | application to adapters | application to entry | domain to adapters | domain to application |
| --- | --- | --- | --- | --- | --- |
| vox | 3 | 118 | 6 | 11 | 8 |
| quarry | | 221 | 1 | 29 | 24 |
| z-spec | 3 | 18 | 1 | | |
| lux | 6 | 58 | 5 | 76 | 14 |

The three refusals are correct and fail closed: the committed
`[tool.oo-ratchet.layers]` tables no longer cover modules added since they were
written. The violation counts above come from `layers --json` and are valid
anyway; the baseline cannot be written until the table is completed.
`layers --suggest` ran on all four and exits 0, writes nothing. Its summary
lines:

| Adopter | Ring-assigned (declaration or name) | From entry evidence | Conflicts | Unclassified |
| --- | --- | --- | --- | --- |
| vox | 318 of 632 | 3 | 137 | 174 |
| quarry | 312 of 494 | 1 | 133 | 48 |
| z-spec | 37 of 63 | 0 | 19 | 7 |
| lux | 625 of 977 | 0 | 177 | 175 |

Lux already runs its own layer gate (`tools/layer_contract.py`,
`.layer-baseline.json`, `make check-layers`). Adopting `oo-ratchet layers`
there means retiring or running beside that tool.

## (d) `design --shadow-check REF --enforce`

Exit status, enforce / plain (plain always 0):

| Adopter | HEAD~3 | HEAD~8 | Added gate-capable findings |
| --- | --- | --- | --- |
| vox | 0 | 0 | 0 |
| quarry | **1** | **1** | HEAD~3: 18 `layer-import` findings in `daemon/collection_finalize_job`, `delta_submit`, `purge_recheck`, `optimize_step`, `table_finalizer`, `table_upkeep`; also one `domain-io` (`post_sync_gc` imports `pathlib`) |
| z-spec | 0 | 0 | 0 |
| lux | 0 | **1** | HEAD~8: 4 `layer-import` findings (`hub.display_peripheral_port`: `DialRef`, `DisplayRequests`, `WriteSeat`; `hub.peripherals`: `ClientRegistry`) |

These are real new layer imports in recent adopter commits, so `--enforce`
would have refused them. Also checked: `--shadow-check origin/main --enforce`
(vox) exits 0; `--enforce` without `--shadow-check` exits 2 with
`--enforce needs --shadow-check`; z-spec's `--shadow-check REF --json` form,
with and without `--enforce`, exits 0 and emits valid JSON.

## Demo (docs/WORKFLOW.md form): vox modules failing a target

`oo-ratchet oo src/punt_vox/ --threshold` from the vox copy, counting files
with at least one FAIL row (script `.tmp/failcount.py`):

| Version | Files scanned | Files failing a target |
| --- | --- | --- |
| 0.4.0 | 632 | 25 |
| this checkout | 632 | 5 |

Aggregate rows: `module_size` target 300 (old) vs 400 (new), no
`method_ratio` row in the new output. The new run's 5 failing files are 2 on
`module_size`, 1 on `init_violations`, 1 on `avg_complexity` and 1 on
`avg_params`. The CHANGELOG says "22 to 5"; the old count on this vox commit
is 25, and the new count matches.

## What changes for each adopter at 0.7.0

| Adopter | Pin bump | New files | New CI steps | Behaviour change they see |
| --- | --- | --- | --- | --- |
| vox | `0.4.0` to `0.7.0` | `.oo-layers-baseline.json`, `.oo-layers-audit.jsonl` | `layers --check` (PR with merge-base `--base-ref`; main with `HEAD~1 --require-base --tripwire`, plus `--allow-config-change` in the adoption PR only); optional `design ... --enforce` | module-size target 400; ratio metrics ungated; ceiling metrics neither regress nor improve under target; domain-purity edges; the table needs 149 modules assigned first |
| quarry | `0.4.0` to `0.7.0` | same two files | same; main-push OO gate has no `--allow-no-improvement` | same; table needs 7 modules assigned; `design --enforce` would refuse recent `layer-import` additions |
| z-spec | `0.4.0` to `0.7.0` | same two files | same; the table is complete, so the baseline (25 edges) can be written at once | 4 of the last 15 commits would fail the must-improve rule on PRs |
| lux | `0.6.0` to `0.7.0` | same two files; decide the fate of `.layer-baseline.json` and `tools/layer_contract.py` | `check-layers` can switch to `oo-ratchet layers` for both source sets | main-push OO gate has no `--allow-no-improvement`; table needs 14 modules assigned; `design --enforce` would refuse 4 layer imports at HEAD~8 |

No adopter needs a rebaseline: every existing `.oo-baseline.json`,
`.oo-coupling-baseline.json` and `.suppression-baseline.json` loaded and
compared without error (extra baseline fields are ignored).

## Incompatibilities and findings

1. The must-improve rule is stricter for under-target edits (see replay).
   Intended per PL-1685 and PL-1712, but it fails commits the 0.4.0 and
   0.6.0 gates passed. Quarry and lux main-push gates will go red on such
   commits; vox and z-spec only on PRs. The 0.7.0 release note should state
   this next to "Adopters pass changes the gate used to refuse": the reverse
   also holds.
2. `layers --update` refuses vox, quarry and lux until their layer tables
   cover every module (149, 7 and 14 unassigned). This is the fail-closed
   design, not a defect. The adopter PR that adds the baseline must also
   finish the table. `layers --suggest` supplies starter text.
3. Domain-purity edges (PL-1711) are in the violation counts above: io edges
   vox 22, quarry 20, z-spec 3, lux 12. `--allow-config-change` is needed once
   per adopter.
4. `design --enforce` is opt-in. Turned on today it fails quarry at HEAD~3 and
   HEAD~8 and lux at HEAD~8 for real layer imports.
5. No bug found in oo-ratchet. No failing-test or fix commits were made. The
   only commit in this worktree is this document.

## Verdict

- z-spec: yes, a pin bump plus the layers baseline (table complete).
- vox: pin bump plus layers adoption; the layers adoption includes assigning
  149 modules.
- quarry: pin bump plus layers adoption (7 modules to assign); its main-push
  OO gate needs `--allow-no-improvement` or it goes red on trim-only commits.
- lux: pin bump plus layers adoption (14 modules to assign) and a decision on
  its own layer tool; same main-push OO gate caveat as quarry.

Nothing in the gates, state-file formats or CLI flags the four adopters use
broke at 0.7.0. The only forced work beyond the pin bump is the layers table
completion and the must-improve behaviour above.
